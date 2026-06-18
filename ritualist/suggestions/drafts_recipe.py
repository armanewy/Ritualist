from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import re
from typing import Any

from pydantic import TypeAdapter

from ritualist.actions.metadata import ActionMetadata
from ritualist.actions.registry import ActionRegistry, create_default_registry
from ritualist.models import AssertionStep, Recipe, WorkflowStep
from ritualist.suggestions.models import Suggestion, SuggestionKind
from ritualist.suggestions.review import require_approval_for_draft
from ritualist.templating import collect_template_variables, render_template_data


DRAFT_RECIPE_SCHEMA_VERSION = "ritualist.suggestion.recipe_draft.v1"
DRAFT_RECIPE_STATUS = "disabled"
MAX_DRAFT_STEPS = 50
MAX_TEXT_LENGTH = 500

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SAFE_VARIABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")
_PLACEHOLDER_RE = re.compile(
    r"^(?:{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}|\$\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\})$"
)
_MISSING_MARKERS = frozenset(
    {
        "",
        "[missing]",
        "<missing>",
        "missing",
        "[redacted]",
        "redacted",
        "tbd",
        "todo",
        "none",
        "null",
    }
)
_RECIPE_MAPPING_KEYS = ("proposed_recipe", "draft_recipe", "recipe")
_STEP_LIST_KEYS = ("steps", "recipe_steps", "draft_steps")
_NESTED_STEP_LIST_FIELDS = frozenset({"steps", "preflight", "verify", "then", "else", "on_timeout"})
_ASSERTION_LIST_FIELDS = frozenset({"preflight", "verify"})
_WINDOW_MATCH_ACTIONS = frozenset(
    {
        "assert.window_exists",
        "wait.for_window",
        "wait.for_window_gone",
        "window.focus",
        "window.maximize",
        "window.minimize",
        "window.wait",
    }
)
_BROWSER_LOCATOR_ACTIONS = frozenset({"browser.element_visible"})
_BROWSER_TITLE_MATCH_ACTIONS = frozenset({"browser.wait_title"})
_BROWSER_URL_MATCH_ACTIONS = frozenset({"browser.wait_url"})
_SCRIPT_OR_MARKUP_RE = re.compile(
    r"<\s*/?\s*(?:html|script|style|iframe|object|embed|form|input|button)\b"
    r"|\bon[A-Za-z]+\s*="
    r"|(?<![\w])(?:javascript|data|vbscript):"
    r"|\b(?:eval|Function|setTimeout|setInterval)\s*\("
    r"|\.(?:ps1|py|js|mjs|cjs|sh|bash|bat|cmd|vbs|qml|html?|hta)\b",
    re.IGNORECASE,
)
_SHELL_NAME_RE = re.compile(
    r"(?<![\w.-])(?:powershell|pwsh|cmd|cmd\.exe|bash|sh|sh\.exe|python|python3|"
    r"node|npm|npx|wscript|cscript)(?![\w.-])",
    re.IGNORECASE,
)
_SHELL_OPERATOR_RE = re.compile(r"&&|\|\||[|<>`]|(?:^|\s)(?:-Command|-EncodedCommand|-c)(?:\s|$)")


class RecipeDraftBuildError(ValueError):
    """Raised when an approved suggestion cannot produce a usable recipe draft."""


@dataclass(frozen=True)
class _OmittedStep:
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"reason": self.reason}


@dataclass
class _DraftBuildState:
    registry: ActionRegistry
    suggestion: Suggestion
    candidate_variables: dict[str, Any]
    missing_inputs: tuple[str, ...]
    variables: dict[str, Any] = field(default_factory=dict)
    variable_hints: dict[str, str] = field(default_factory=dict)
    diagnostic_variables: dict[str, Any] = field(default_factory=dict)
    required_capabilities: set[str] = field(default_factory=set)
    omitted_steps: list[_OmittedStep] = field(default_factory=list)
    _used_missing_input_indexes: set[int] = field(default_factory=set)

    def variable_for(
        self,
        *,
        action: str,
        field_name: str,
        hint: str | None = None,
        requested_name: object = None,
    ) -> str:
        raw_name = _clean_text(requested_name)
        if not raw_name:
            raw_name = self._next_missing_input(field_name) or f"{action}_{field_name}"
        name = _safe_variable_name(raw_name, fallback=f"{action}_{field_name}")
        base = name
        offset = 2
        while name in self.variables:
            name = f"{base}_{offset}"[:64]
            offset += 1
        self.variable_hints.setdefault(
            name,
            hint
            or f"Set {field_name} for {action} before enabling this disabled draft.",
        )
        self.diagnostic_variables.setdefault(name, _diagnostic_value(action, field_name))
        return name

    def register_template_references(self, value: Any) -> None:
        known = set(self.variables) | set(self.candidate_variables)
        for name in sorted(collect_template_variables(value)):
            root = name.split(".", 1)[0]
            if name in known or root in known:
                continue
            safe_name = _safe_variable_name(name, fallback="draft_value")
            self.variable_hints.setdefault(
                safe_name,
                "Set this value before enabling this disabled draft.",
            )
            self.diagnostic_variables.setdefault(safe_name, "draft value")

    def diagnostic_context(self) -> dict[str, Any]:
        context = dict(self.candidate_variables)
        context.update(self.diagnostic_variables)
        return context

    def _next_missing_input(self, field_name: str) -> str:
        for index, value in enumerate(self.missing_inputs):
            if index in self._used_missing_input_indexes:
                continue
            if not _missing_input_matches_field(value, field_name):
                continue
            self._used_missing_input_indexes.add(index)
            return value
        return ""


def build_draft_recipe(
    suggestion: Suggestion | Mapping[str, Any],
    *,
    registry: ActionRegistry | None = None,
) -> dict[str, Any]:
    """Return disabled, sanitized recipe-draft data for an approved suggestion.

    The builder does not write a recipe file, install a pack, enable a draft, or
    run any runtime action. It only returns a recipe document inside a disabled
    draft envelope.
    """

    approved = _approved_suggestion(suggestion)
    if approved.kind is not SuggestionKind.RITUAL_RECIPE:
        raise RecipeDraftBuildError("Only ritual recipe suggestions can produce recipe drafts.")

    # Only consume fields that were normalized into the approved Suggestion.
    # Raw mapping extras are not part of the review token and must not become
    # draft behavior after approval.
    raw_source = approved.to_dict()
    candidate = _recipe_candidate(raw_source)
    candidate_variables = _sanitize_variables(_mapping(candidate.get("variables")))
    state = _DraftBuildState(
        registry=registry or create_default_registry(),
        suggestion=approved,
        candidate_variables=candidate_variables,
        missing_inputs=approved.missing_inputs,
        variables=dict(candidate_variables),
    )

    preflight = _sanitize_step_list(
        _sequence(candidate.get("preflight")),
        state=state,
        assertion_context=True,
    )
    steps = _sanitize_step_list(
        _recipe_steps(candidate, raw_source, approved),
        state=state,
        assertion_context=False,
    )
    verify = _sanitize_step_list(
        _sequence(candidate.get("verify")),
        state=state,
        assertion_context=True,
    )

    if not steps:
        raise RecipeDraftBuildError("Approved suggestion did not contain usable recipe steps.")

    recipe = _recipe_document(
        candidate=candidate,
        suggestion=approved,
        state=state,
        preflight=preflight,
        steps=steps,
        verify=verify,
    )
    _validate_recipe_document(recipe, state)

    return {
        "schema_version": DRAFT_RECIPE_SCHEMA_VERSION,
        "status": DRAFT_RECIPE_STATUS,
        "suggestion_id": approved.id,
        "review_token": approved.approval.review_token if approved.approval else "",
        "requires_doctor_before_enable": True,
        "doctor_required_before_enable": True,
        "creation_side_effects": {
            "installed": False,
            "enabled": False,
            "ran": False,
            "wrote_files": False,
        },
        "missing_variables": sorted(
            name
            for name in state.variable_hints
            if name not in state.variables
        ),
        "omitted_steps": [item.to_dict() for item in state.omitted_steps],
        "recipe": recipe,
    }


def build_recipe_draft(
    suggestion: Suggestion | Mapping[str, Any],
    *,
    registry: ActionRegistry | None = None,
) -> dict[str, Any]:
    return build_draft_recipe(suggestion, registry=registry)


def create_draft_recipe_data(
    suggestion: Suggestion | Mapping[str, Any],
    *,
    registry: ActionRegistry | None = None,
) -> dict[str, Any]:
    return build_draft_recipe(suggestion, registry=registry)


def _approved_suggestion(source: Suggestion | Mapping[str, Any]) -> Suggestion:
    if isinstance(source, Suggestion):
        return require_approval_for_draft(source)
    if isinstance(source, Mapping):
        return require_approval_for_draft(Suggestion.from_mapping(source))
    raise RecipeDraftBuildError("recipe draft source must be a Suggestion or mapping")


def _recipe_candidate(source: Mapping[str, Any]) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for key in _RECIPE_MAPPING_KEYS:
        value = source.get(key)
        if isinstance(value, Mapping):
            candidate.update(dict(value))
            break
    if not candidate and any(key in source for key in ("steps", "preflight", "verify")):
        candidate.update(
            {
                key: source[key]
                for key in ("id", "name", "description", "variables", "environment", "preflight", "steps", "verify")
                if key in source
            }
        )
    return candidate


def _recipe_steps(
    candidate: Mapping[str, Any],
    source: Mapping[str, Any],
    suggestion: Suggestion,
) -> list[Any]:
    steps: list[Any] = []
    for key in _STEP_LIST_KEYS:
        steps.extend(_sequence(candidate.get(key)))
    proposed_actions = _sequence(source.get("proposed_actions"))
    for action in proposed_actions:
        if not isinstance(action, Mapping):
            continue
        for key in _STEP_LIST_KEYS:
            steps.extend(_sequence(action.get(key)))
    if steps:
        return steps[:MAX_DRAFT_STEPS]
    return _fallback_review_steps(suggestion)


def _fallback_review_steps(suggestion: Suggestion) -> list[dict[str, Any]]:
    items = [
        _clean_text(action.get("label") or action.get("title") or action.get("description") or "Review suggested step")
        for action in suggestion.proposed_actions
        if isinstance(action, Mapping)
    ]
    if not items:
        items = ["Review approved ritual recipe suggestion."]
    steps: list[dict[str, Any]] = [
        {
            "action": "human.checklist",
            "prompt": "Review approved suggestion before editing this disabled draft.",
            "items": items[:MAX_DRAFT_STEPS],
        }
    ]
    for name in suggestion.missing_inputs[:MAX_DRAFT_STEPS]:
        steps.append(
            {
                "action": "human.prompt",
                "prompt": f"Provide {{{{ {name} }}}} before enabling this draft.",
            }
        )
    steps.append(
        {
            "action": "wait.for_user",
            "prompt": "Run Doctor after filling draft variables.",
        }
    )
    return steps


def _sanitize_step_list(
    raw_steps: Sequence[Any],
    *,
    state: _DraftBuildState,
    assertion_context: bool,
    depth: int = 0,
) -> list[dict[str, Any]]:
    if depth > 4:
        state.omitted_steps.append(_OmittedStep("nested_steps_too_deep"))
        return []
    sanitized: list[dict[str, Any]] = []
    for raw_step in list(raw_steps)[:MAX_DRAFT_STEPS]:
        step = _sanitize_step(raw_step, state=state, assertion_context=assertion_context, depth=depth)
        if step is None:
            continue
        sanitized.append(step)
    return sanitized


def _sanitize_step(
    raw_step: Any,
    *,
    state: _DraftBuildState,
    assertion_context: bool,
    depth: int,
) -> dict[str, Any] | None:
    if not isinstance(raw_step, Mapping):
        state.omitted_steps.append(_OmittedStep("step_not_mapping"))
        return None
    action = _clean_text(raw_step.get("action"))
    if not action:
        state.omitted_steps.append(_OmittedStep("missing_action"))
        return None
    try:
        metadata = state.registry.metadata(action)
    except KeyError:
        state.omitted_steps.append(_OmittedStep("unknown_action"))
        return None
    if assertion_context and metadata.category != "assert":
        state.omitted_steps.append(_OmittedStep("non_assertion_in_assertion_list"))
        return None
    if action == "desktop.click_text" and not _desktop_click_is_scoped_and_gated(raw_step):
        state.omitted_steps.append(_OmittedStep("desktop_click_requires_scope_and_confirmation"))
        return None

    allowed_fields = {"action", *metadata.required_params, *metadata.optional_params}
    step: dict[str, Any] = {"action": action}
    try:
        for key, value in raw_step.items():
            field_name = str(key)
            if field_name == "action" or field_name not in allowed_fields:
                continue
            if field_name in _NESTED_STEP_LIST_FIELDS:
                step[field_name] = _sanitize_nested_steps(
                    field_name,
                    value,
                    state=state,
                    depth=depth + 1,
                )
                continue
            if _is_missing_value(value):
                if field_name in metadata.required_params or _explicit_missing_variable(value):
                    step[field_name] = _variable_reference(
                        state.variable_for(action=action, field_name=field_name, requested_name=_missing_name(value))
                    )
                continue
            step[field_name] = _sanitize_value(value, action=action, field_name=field_name)
        _fill_required_fields(step, metadata, state)
        _fill_shape_required_fields(step, state)
    except RecipeDraftBuildError as exc:
        state.omitted_steps.append(_OmittedStep(str(exc)))
        return None

    state.required_capabilities.update(metadata.required_capabilities)
    state.register_template_references(step)
    if not _step_validates(step, state=state, assertion_context=assertion_context):
        state.omitted_steps.append(_OmittedStep("invalid_structured_step"))
        return None
    return step


def _sanitize_nested_steps(
    field_name: str,
    value: Any,
    *,
    state: _DraftBuildState,
    depth: int,
) -> list[dict[str, Any]]:
    assertion_context = field_name in _ASSERTION_LIST_FIELDS
    return _sanitize_step_list(
        _sequence(value),
        state=state,
        assertion_context=assertion_context,
        depth=depth,
    )


def _fill_required_fields(
    step: dict[str, Any],
    metadata: ActionMetadata,
    state: _DraftBuildState,
) -> None:
    action = step["action"]
    for field_name in metadata.required_params:
        if _is_missing_value(step.get(field_name)):
            step[field_name] = _variable_reference(
                state.variable_for(action=action, field_name=field_name)
            )


def _fill_shape_required_fields(step: dict[str, Any], state: _DraftBuildState) -> None:
    action = str(step.get("action") or "")
    if action in _WINDOW_MATCH_ACTIONS and not (step.get("title_contains") or step.get("process_name")):
        step["title_contains"] = _variable_reference(
            state.variable_for(action=action, field_name="title_contains")
        )
    if action in _BROWSER_LOCATOR_ACTIONS and not (
        step.get("text") or step.get("role") or step.get("test_id")
    ):
        step["text"] = _variable_reference(state.variable_for(action=action, field_name="text"))
    if action in _BROWSER_TITLE_MATCH_ACTIONS and not (
        step.get("title") or step.get("title_contains")
    ):
        step["title_contains"] = _variable_reference(
            state.variable_for(action=action, field_name="title_contains")
        )
    if action in _BROWSER_URL_MATCH_ACTIONS and not (step.get("url") or step.get("url_contains")):
        step["url_contains"] = _variable_reference(
            state.variable_for(action=action, field_name="url_contains")
        )


def _sanitize_value(value: Any, *, action: str, field_name: str) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _sanitize_string(value, action=action, field_name=field_name)
    if isinstance(value, Mapping):
        return {
            _safe_mapping_key(key): _sanitize_value(item, action=action, field_name=field_name)
            for key, item in value.items()
            if _safe_mapping_key(key)
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            _sanitize_value(item, action=action, field_name=field_name)
            for item in list(value)[:MAX_DRAFT_STEPS]
        ]
    return _sanitize_string(str(value), action=action, field_name=field_name)


def _sanitize_string(value: str, *, action: str, field_name: str) -> str:
    text = _clean_text(value)
    if not text:
        return text
    if _placeholder_name(text):
        return _variable_reference(_safe_variable_name(_placeholder_name(text), fallback=field_name))
    if _SCRIPT_OR_MARKUP_RE.search(text):
        raise RecipeDraftBuildError("script_or_markup_blocked")
    if _shell_text_is_blocked(text, action=action, field_name=field_name):
        raise RecipeDraftBuildError("shell_snippet_blocked")
    if action == "browser.open" and field_name == "url" and _blocked_browser_url(text):
        raise RecipeDraftBuildError("unsafe_browser_url_blocked")
    return text[:MAX_TEXT_LENGTH]


def _shell_text_is_blocked(text: str, *, action: str, field_name: str) -> bool:
    if _SHELL_NAME_RE.search(text):
        return True
    if action == "app.launch" and field_name in {"command", "args", "cwd", "env"}:
        return bool(_SHELL_OPERATOR_RE.search(text))
    return False


def _blocked_browser_url(text: str) -> bool:
    normalized = text.strip().casefold()
    if _placeholder_name(normalized):
        return False
    return normalized.startswith(("javascript:", "data:", "vbscript:", "file:"))


def _desktop_click_is_scoped_and_gated(raw_step: Mapping[str, Any]) -> bool:
    scope = _clean_text(raw_step.get("window_title_contains"))
    return bool(scope and raw_step.get("requires_confirmation") is True)


def _step_validates(
    step: Mapping[str, Any],
    *,
    state: _DraftBuildState,
    assertion_context: bool,
) -> bool:
    adapter = TypeAdapter(AssertionStep if assertion_context else WorkflowStep)
    try:
        adapter.validate_python(render_template_data(dict(step), state.diagnostic_context()))
        return True
    except Exception:  # noqa: BLE001 - pydantic keeps useful details internally; omit raw data.
        return False


def _recipe_document(
    *,
    candidate: Mapping[str, Any],
    suggestion: Suggestion,
    state: _DraftBuildState,
    preflight: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    verify: list[dict[str, Any]],
) -> dict[str, Any]:
    environment = _environment(candidate, state)
    recipe = {
        "version": "0.1",
        "id": _recipe_id(candidate.get("id") or f"{suggestion.title} draft"),
        "name": _recipe_name(candidate.get("name") or suggestion.title),
        "description": _recipe_description(candidate.get("description") or suggestion.description),
        "variables": dict(sorted(state.variables.items())),
        "environment": environment,
        "preflight": preflight,
        "steps": steps,
        "verify": verify,
    }
    return recipe


def _environment(candidate: Mapping[str, Any], state: _DraftBuildState) -> dict[str, Any]:
    raw_environment = _mapping(candidate.get("environment"))
    environment: dict[str, Any] = {}
    os_values = [
        item
        for item in _sequence(raw_environment.get("os"))
        if isinstance(item, str) and item in {"windows", "macos", "linux"}
    ]
    if os_values:
        environment["os"] = list(dict.fromkeys(os_values))
    required_capabilities = set(state.required_capabilities)
    required_capabilities.update(
        item
        for item in _sequence(raw_environment.get("required_capabilities"))
        if isinstance(item, str) and item
    )
    environment["required_capabilities"] = sorted(required_capabilities)
    environment["expected_windows"] = [
        value
        for value in (
            _sanitize_expected_window(item)
            for item in _sequence(raw_environment.get("expected_windows"))
        )
        if value
    ]
    environment["expected_labels"] = [
        value
        for value in (
            _sanitize_expected_label(item)
            for item in _sequence(raw_environment.get("expected_labels"))
        )
        if value
    ]
    raw_hints = _mapping(raw_environment.get("variable_hints"))
    hints = {
        _safe_variable_name(key, fallback="draft_value"): _clean_text(value)[:MAX_TEXT_LENGTH]
        for key, value in raw_hints.items()
        if _safe_variable_name(key, fallback="")
    }
    hints.update(state.variable_hints)
    environment["variable_hints"] = dict(sorted(hints.items()))
    return environment


def _sanitize_expected_window(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in ("title_contains", "process_name"):
        text = _clean_text(value.get(key))
        if text:
            result[key] = text
    return result


def _sanitize_expected_label(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in ("window_title_contains", "text", "control_type"):
        text = _clean_text(value.get(key))
        if text:
            result[key] = text
    if "exact" in value:
        result["exact"] = bool(value["exact"])
    return result


def _validate_recipe_document(recipe: Mapping[str, Any], state: _DraftBuildState) -> None:
    try:
        Recipe.model_validate(render_template_data(dict(recipe), state.diagnostic_context()))
    except Exception as exc:  # noqa: BLE001 - report a sanitized draft-builder error.
        raise RecipeDraftBuildError("Sanitized draft recipe did not validate.") from exc


def _sanitize_variables(raw_variables: Mapping[str, Any]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for key, value in raw_variables.items():
        name = _safe_variable_name(key, fallback="")
        if not name or _is_missing_value(value):
            continue
        try:
            variables[name] = _sanitize_value(value, action="variables", field_name=name)
        except RecipeDraftBuildError:
            continue
    return variables


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return _clean_text(value).casefold() in _MISSING_MARKERS
    if isinstance(value, Mapping):
        return bool(_explicit_missing_variable(value))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value) == 0
    return False


def _explicit_missing_variable(value: Any) -> bool:
    return bool(_missing_name(value))


def _missing_name(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    for key in ("variable", "var", "input_id", "missing_input", "name"):
        text = _clean_text(value.get(key))
        if text:
            return text
    return ""


def _missing_input_matches_field(value: str, field_name: str) -> bool:
    value_tokens = _token_set(value)
    field_tokens = _token_set(field_name)
    if value_tokens.intersection(field_tokens):
        return True
    aliases = {
        "url": {"address", "domain", "href", "link", "site", "website"},
        "url_contains": {"address", "domain", "href", "link", "site", "website"},
        "command": {"app", "application", "executable", "program", "target"},
        "path": {"directory", "file", "folder", "root"},
        "process_name": {"app", "application", "process", "program"},
        "prompt": {"confirmation", "message", "operator", "prompt", "review"},
        "text": {"label", "text"},
        "title_contains": {"title", "window"},
        "window_title_contains": {"title", "window"},
    }
    return bool(value_tokens.intersection(aliases.get(field_name, set())))


def _token_set(value: object) -> set[str]:
    return {token for token in _TOKEN_RE.split(_clean_text(value).casefold()) if token}


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return []


def _safe_mapping_key(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    normalized = text.replace("-", "_")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", normalized):
        return ""
    return normalized


def _recipe_id(value: object) -> str:
    text = _clean_text(value)
    if _SAFE_ID_RE.fullmatch(text):
        return text
    slug = _safe_variable_name(text, fallback="suggested_ritual")
    slug = slug.replace("_", "-")
    if not slug[0].isalnum():
        slug = f"draft-{slug}"
    if "draft" not in slug.casefold():
        slug = f"{slug}-draft"
    return slug[:64].rstrip("-_")


def _recipe_name(value: object) -> str:
    text = _clean_text(value) or "Suggested Ritual Draft"
    if "draft" not in text.casefold():
        text = f"{text} draft"
    return text[:MAX_TEXT_LENGTH]


def _recipe_description(value: object) -> str:
    text = _clean_text(value) or "Disabled recipe draft created from an approved suggestion."
    suffix = " Review variables and run Doctor before enabling."
    if "doctor" not in text.casefold():
        text = f"{text}{suffix}"
    return text[:MAX_TEXT_LENGTH]


def _safe_variable_name(value: object, *, fallback: str) -> str:
    text = _clean_text(value)
    if not text:
        text = fallback
    text = text.replace(".", "_").replace("-", "_")
    text = _TOKEN_RE.sub("_", text).strip("_").casefold()
    if not text:
        text = _TOKEN_RE.sub("_", fallback).strip("_").casefold() or "draft_value"
    if not text[0].isalpha() and text[0] != "_":
        text = f"draft_{text}"
    text = text[:64].rstrip("_") or "draft_value"
    if not _SAFE_VARIABLE_RE.fullmatch(text):
        return "draft_value"
    return text


def _variable_reference(name: str) -> str:
    return f"{{{{ {name} }}}}"


def _placeholder_name(value: str) -> str:
    match = _PLACEHOLDER_RE.fullmatch(_clean_text(value))
    if not match:
        return ""
    return match.group(1) or match.group(2) or ""


def _diagnostic_value(action: str, field_name: str) -> Any:
    if field_name in {"seconds", "timeout_seconds"}:
        return 1.0
    if field_name in {"x", "y"}:
        return 1
    if field_name in {"width", "height"}:
        return 640
    if field_name == "keys":
        return ["Ctrl", "S"]
    if field_name in {"items", "evidence"}:
        return ["Review draft value"]
    if field_name in {"condition", "when"}:
        return {"type": "path.exists", "path": "RITUALIST_DRAFT_PLACEHOLDER"}
    if field_name == "args":
        return []
    if field_name == "env":
        return {}
    if field_name == "url":
        return "https://example.test"
    if field_name == "command":
        return "RITUALIST_DRAFT_PLACEHOLDER"
    if field_name == "path":
        return "RITUALIST_DRAFT_PLACEHOLDER"
    if field_name == "process_name":
        return "RITUALIST_DRAFT_PLACEHOLDER"
    if field_name in {"title", "title_contains", "window_title_contains"}:
        return "Ritualist Draft"
    if field_name in {"prompt", "message", "text", "accessible_name", "test_id"}:
        return "Review draft value"
    if field_name == "role":
        return "button"
    return "draft value"


def _clean_text(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


__all__ = [
    "DRAFT_RECIPE_SCHEMA_VERSION",
    "DRAFT_RECIPE_STATUS",
    "RecipeDraftBuildError",
    "build_draft_recipe",
    "build_recipe_draft",
    "create_draft_recipe_data",
]
