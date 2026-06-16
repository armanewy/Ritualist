from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from ritualist.actions.catalog import SIDE_EFFECT_LABELS, create_action_catalog
from ritualist.actions.registry import ActionRegistry, create_default_registry


class PackReviewDecision(StrEnum):
    RUN_DOCTOR = "run_doctor"
    DRY_RUN = "dry_run"
    ENABLE = "enable"
    CANCEL = "cancel"


@dataclass(frozen=True)
class PackReviewAction:
    action_name: str
    side_effect_level: str = ""
    side_effect_label: str = ""
    required_capabilities: tuple[str, ...] = ()
    safety_warnings: tuple[str, ...] = ()
    blocked_by_policy: bool = False

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["required_capabilities"] = list(self.required_capabilities)
        data["safety_warnings"] = list(self.safety_warnings)
        return data


@dataclass(frozen=True)
class PackImportReview:
    pack_name: str
    pack_version: str = ""
    author: str = ""
    actions: tuple[PackReviewAction, ...] = ()
    required_variables: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    safety_warnings: tuple[str, ...] = ()
    readme: str = ""
    validation_errors: tuple[str, ...] = ()
    policy_failures: tuple[str, ...] = ()
    schema_version: str = "pack_import_review.v1"

    @property
    def enable_allowed(self) -> bool:
        return not self.validation_errors and not self.policy_failures

    @property
    def enable_blockers(self) -> tuple[str, ...]:
        return (*self.validation_errors, *self.policy_failures)

    @property
    def action_names(self) -> tuple[str, ...]:
        return tuple(action.action_name for action in self.actions)

    @property
    def side_effect_levels(self) -> tuple[str, ...]:
        return _unique(
            action.side_effect_level for action in self.actions if action.side_effect_level
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pack_name": self.pack_name,
            "pack_version": self.pack_version,
            "author": self.author,
            "actions": [action.to_dict() for action in self.actions],
            "action_names": list(self.action_names),
            "side_effect_levels": list(self.side_effect_levels),
            "required_variables": list(self.required_variables),
            "required_capabilities": list(self.required_capabilities),
            "safety_warnings": list(self.safety_warnings),
            "readme": self.readme,
            "validation_errors": list(self.validation_errors),
            "policy_failures": list(self.policy_failures),
            "enable_allowed": self.enable_allowed,
            "enable_blockers": list(self.enable_blockers),
        }

    def to_qml(self) -> dict[str, object]:
        return self.to_dict()


def build_pack_import_review(
    summary: Mapping[str, Any] | object,
    *,
    registry: ActionRegistry | None = None,
) -> PackImportReview:
    """Build GUI/Home review data from a preloaded pack summary.

    This function does not read pack files, enable recipes, or run recipes. Callers should load
    and validate pack data off the UI thread, then pass the resulting summary here before
    showing review UI.
    """

    resolved_registry = registry or create_default_registry()
    catalog = create_action_catalog(resolved_registry)
    pack_info = (
        _mapping_or_object(_first_value(summary, ("pack", "manifest", "metadata"))) or summary
    )
    manifest = _mapping_or_object(_first_value(summary, ("manifest",))) or pack_info
    raw_actions = _first_value(summary, ("actions_requested", "actions", "action_names"))
    if raw_actions is None:
        raw_actions = _first_value(manifest, ("required_actions",))

    actions, action_validation_errors = _review_actions(
        raw_actions,
        registry=resolved_registry,
        catalog=catalog,
    )
    summary_capabilities = _string_tuple(
        _first_value(summary, ("required_capabilities", "capabilities"))
    )
    if not summary_capabilities:
        summary_capabilities = _string_tuple(_first_value(manifest, ("required_capabilities",)))
    required_capabilities = _unique(
        [
            *summary_capabilities,
            *(capability for action in actions for capability in action.required_capabilities),
        ]
    )
    safety_warnings = _unique(
        [
            *_string_tuple(_first_value(summary, ("safety_warnings", "warnings"))),
            *(warning for action in actions for warning in action.safety_warnings),
        ]
    )
    validation_errors = _unique(
        [
            *_string_tuple(_first_value(summary, ("validation_errors", "errors"))),
            *action_validation_errors,
        ]
    )
    policy_failures = _unique(
        [
            *_string_tuple(_first_value(summary, ("policy_failures", "policy_errors"))),
            *(
                f"Action '{action.action_name}' is blocked in imported recipe packs."
                for action in actions
                if action.blocked_by_policy
            ),
        ]
    )

    return PackImportReview(
        pack_name=_first_text(pack_info, ("name", "pack_name", "title"), fallback="Untitled Pack"),
        pack_version=_first_text(pack_info, ("version", "pack_version"), fallback=""),
        author=_first_text(pack_info, ("author", "pack_author"), fallback=""),
        actions=actions,
        required_variables=_review_variables(summary, manifest),
        required_capabilities=required_capabilities,
        safety_warnings=safety_warnings,
        readme=_first_text(summary, ("readme", "readme_content", "README"), fallback=""),
        validation_errors=validation_errors,
        policy_failures=policy_failures,
    )


def _review_actions(
    raw_actions: object,
    *,
    registry: ActionRegistry,
    catalog: object,
) -> tuple[tuple[PackReviewAction, ...], tuple[str, ...]]:
    actions: list[PackReviewAction] = []
    validation_errors: list[str] = []
    for raw_action in _action_items(raw_actions):
        action_name = _action_name(raw_action)
        if not action_name:
            validation_errors.append("Pack summary contains an action without a name.")
            continue
        action_mapping = raw_action if isinstance(raw_action, Mapping) else {}
        metadata = None
        catalog_entry = None
        try:
            metadata = registry.metadata(action_name)
            catalog_entry = catalog.entry(action_name)
        except KeyError:
            validation_errors.append(f"Action '{action_name}' is not registered.")

        side_effect_level = _first_text(
            action_mapping,
            ("side_effect_level", "sideEffectLevel"),
            fallback=getattr(metadata, "side_effect_level", ""),
        )
        side_effect_label = _first_text(
            action_mapping,
            ("side_effect_label", "sideEffectLabel"),
            fallback=_side_effect_label(side_effect_level),
        )
        required_capabilities = _string_tuple(
            _first_value(action_mapping, ("required_capabilities", "capabilities"))
        )
        if not required_capabilities and metadata is not None:
            required_capabilities = tuple(metadata.required_capabilities)

        safety_warnings = _string_tuple(
            _first_value(action_mapping, ("safety_warnings", "warnings"))
        )
        if not safety_warnings and catalog_entry is not None:
            safety_warnings = tuple(catalog_entry.safety_warnings)

        allowed_raw = _first_value(
            action_mapping,
            ("allowed_in_imported_packs", "allowedInImportedPacks"),
        )
        allowed = _optional_bool(allowed_raw)
        if allowed is None and metadata is not None:
            allowed = metadata.allowed_in_imported_packs

        actions.append(
            PackReviewAction(
                action_name=action_name,
                side_effect_level=side_effect_level,
                side_effect_label=side_effect_label,
                required_capabilities=required_capabilities,
                safety_warnings=safety_warnings,
                blocked_by_policy=allowed is False,
            )
        )
    return tuple(actions), tuple(validation_errors)


def _action_items(raw_actions: object) -> tuple[object, ...]:
    if raw_actions is None:
        return ()
    if isinstance(raw_actions, str):
        return (raw_actions,)
    if isinstance(raw_actions, Mapping):
        if any(key in raw_actions for key in ("action", "action_name", "name")):
            return (raw_actions,)
        if "items" in raw_actions:
            return _action_items(raw_actions["items"])
        return tuple(raw_actions)
    if isinstance(raw_actions, Sequence):
        return tuple(raw_actions)
    return (raw_actions,)


def _action_name(raw_action: object) -> str:
    if isinstance(raw_action, str):
        return raw_action.strip()
    return _first_text(raw_action, ("action", "action_name", "name"), fallback="")


def _review_variables(summary: object, manifest: object) -> tuple[str, ...]:
    raw = _first_value(summary, ("required_variables", "variables", "variable_names"))
    if raw is None:
        raw = _first_value(manifest, ("variables",))
    return _string_tuple(raw)


def _mapping_or_object(value: object) -> object | None:
    if value is None:
        return None
    return value


def _first_text(source: object, names: tuple[str, ...], *, fallback: str) -> str:
    value = _first_value(source, names)
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _first_value(source: object, names: tuple[str, ...]) -> object:
    for name in names:
        if isinstance(source, Mapping) and name in source:
            return source[name]
        if not isinstance(source, Mapping) and hasattr(source, name):
            return getattr(source, name)
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, Mapping):
        return _unique(str(key).strip() for key in value if str(key).strip())
    if isinstance(value, Sequence):
        return _unique(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    return (text,) if text else ()


def _unique(values: Sequence[str] | Any) -> tuple[str, ...]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        unique_values.append(text)
        seen.add(key)
    return tuple(unique_values)


def _side_effect_label(side_effect_level: str) -> str:
    if side_effect_level in SIDE_EFFECT_LABELS:
        return SIDE_EFFECT_LABELS[side_effect_level]  # type: ignore[index]
    return side_effect_level.replace("_", " ").title() if side_effect_level else ""


def _optional_bool(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None
