from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .doctor import DoctorCheck, _check_capability
from .errors import RecipeValidationError, RitualistError
from .models import SAFE_ID_PATTERN, Recipe
from .policy import (
    PolicyFinding,
    PolicyProfile,
    PolicyReport,
    PrimitivePolicyEngine,
    PrimitiveRequirement,
)
from .primitives import (
    PrimitivePlan,
    PrimitivePlanStep,
    PrimitiveRegistry,
    PrimitiveRisk,
    PrimitiveSpec,
    create_primitive_registry,
)
from .paths import recipes_path
from .recipe_loader import load_recipe_document, read_recipe_document
from .templating import collect_template_variables


INTENT_SCHEMA_VERSION = "intent.v1"
PLAN_PREVIEW_SCHEMA_VERSION = "intent.plan_preview.v1"

_RISK_ORDER: dict[PrimitiveRisk, int] = {
    PrimitiveRisk.READ_ONLY: 0,
    PrimitiveRisk.LAUNCHES_APP: 1,
    PrimitiveRisk.CONTROLS_UI: 2,
    PrimitiveRisk.MODIFIES_FILES: 3,
    PrimitiveRisk.RISKY: 4,
}


class IntentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    kind: str
    display_name: str = ""
    description: str = ""
    target: dict[str, Any] | str | None = None
    requested_outcome: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    risk_budget: str = PrimitiveRisk.READ_ONLY.value
    user_visible_summary: str = ""
    schema_version: str = INTENT_SCHEMA_VERSION

    @field_validator("intent_id")
    @classmethod
    def validate_intent_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("intent_id must be a safe filename-like identifier")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("kind must not be blank")
        return text

    @field_validator("risk_budget")
    @classmethod
    def validate_risk_budget(cls, value: str) -> str:
        if value not in {risk.value for risk in PrimitiveRisk}:
            allowed = ", ".join(risk.value for risk in PrimitiveRisk)
            raise ValueError(f"risk_budget must be one of {allowed}")
        return value

    def to_plan_intent(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "intent_id": self.intent_id,
            "kind": self.kind,
            "display_name": self.display_name,
            "description": self.description,
            "target": _redact_mapping(self.target),
            "requested_outcome": self.requested_outcome,
            "constraints": _redact_mapping(self.constraints),
            "preferences": _redact_mapping(self.preferences),
            "risk_budget": self.risk_budget,
            "user_visible_summary": self.user_visible_summary,
        }


@dataclass(frozen=True)
class PlanDoctorReport:
    plan_id: str
    compatibility: str
    checks: tuple[DoctorCheck, ...]
    policy_report: PolicyReport
    schema_version: str = "intent.plan_doctor.v1"

    @property
    def errors_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "error")

    @property
    def warnings_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "warn")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "compatibility": {
                "status": self.compatibility,
                "errors_count": self.errors_count,
                "warnings_count": self.warnings_count,
            },
            "checks": [check.to_dict() for check in self.checks],
            "policy": self.policy_report.to_dict(),
        }


def compile_intent_to_plan(
    intent: IntentSpec,
    *,
    primitive_registry: PrimitiveRegistry | None = None,
) -> PrimitivePlan:
    registry = primitive_registry or create_primitive_registry()
    steps: list[PrimitivePlanStep] = []
    unresolved: list[str] = []
    artifacts: list[str] = []
    verification: list[str] = []
    cleanup: list[str] = []

    if intent.kind == "diagnostics.collect":
        _compile_diagnostics_intent(intent, registry=registry, steps=steps, artifacts=artifacts, verification=verification)
    elif intent.kind in {"workspace.prepare", "target.start", "stream.prepare"}:
        _compile_workspace_intent(intent, registry=registry, steps=steps, unresolved=unresolved)
    elif intent.kind in {"system.repair", "package.provision"}:
        unresolved.append(
            f"{intent.kind} is not supported by v1 planning because mutation primitives are unavailable"
        )
    else:
        unresolved.append(f"no deterministic compiler rule for intent kind '{intent.kind}'")

    cleanup.append("No rollback actions are generated by Intent Plan Compiler v1.")
    cleanup.append("Preview is side-effect free; no cleanup is needed after preview.")
    return _finalize_plan(
        intent.intent_id,
        intent=intent,
        steps=steps,
        registry=registry,
        artifacts_expected=artifacts,
        verification_steps=verification,
        rollback_or_cleanup_notes=cleanup,
        unresolved_questions=unresolved,
    )


def compile_recipe_to_plan(
    recipe: Recipe,
    *,
    source: str | None = None,
    missing_variables: list[str] | None = None,
    primitive_registry: PrimitiveRegistry | None = None,
) -> PrimitivePlan:
    registry = primitive_registry or create_primitive_registry()
    intent = IntentSpec(
        intent_id=f"recipe_{recipe.id}",
        kind="recipe.preview",
        display_name=f"Preview {recipe.name}",
        description="Recipe preview compiled from existing structured steps.",
        target=source or recipe.id,
        requested_outcome="Preview recipe primitive requirements without executing it.",
        risk_budget=PrimitiveRisk.RISKY.value,
        user_visible_summary=f"Preview primitive requirements for {recipe.name}.",
    )
    steps: list[PrimitivePlanStep] = []
    unresolved: list[str] = [
        f"missing variable '{name}'" for name in sorted(missing_variables or [])
    ]
    for index, step in enumerate(recipe.execution_steps, start=1):
        try:
            spec = registry.spec_for_action(step.action)
        except KeyError:
            unresolved.append(f"step {index} action '{step.action}' has no primitive metadata")
            continue
        steps.append(
            PrimitivePlanStep(
                primitive_id=spec.primitive_id,
                action_name=step.action,
                step_name=step.display_name,
                parameters=_step_parameters(step),
                risk=spec.risk,
            )
        )
    return _finalize_plan(
        f"recipe_{recipe.id}",
        intent=intent,
        steps=steps,
        registry=registry,
        verification_steps=(
            "Recipe validation succeeded before plan preview."
            if not missing_variables
            else "Recipe was loaded with placeholder values for missing variables."
        ),
        rollback_or_cleanup_notes=(
            "Preview does not launch apps, click UI, mutate files, or run shell commands.",
        ),
        unresolved_questions=unresolved,
        recipe_id=recipe.id,
    )


def compile_plan_reference(target: str | Path) -> PrimitivePlan:
    candidate = Path(str(target)).expanduser()
    if candidate.exists():
        raw = _read_yaml_mapping(candidate)
        if _looks_like_intent(raw):
            return compile_intent_to_plan(_intent_from_mapping(raw))
        recipe, missing = _load_recipe_raw_for_plan(raw)
        return compile_recipe_to_plan(recipe, source=str(candidate), missing_variables=missing)

    try:
        recipe_path = _resolve_recipe_reference_no_create(target)
        raw = read_recipe_document(recipe_path)
        recipe, missing = _load_recipe_raw_for_plan(raw)
    except RecipeValidationError:
        if _looks_like_path_reference(str(target)):
            raise
        return compile_intent_to_plan(_intent_from_kind(str(target)))
    return compile_recipe_to_plan(recipe, source=str(recipe_path), missing_variables=missing)


def build_plan_doctor_report(
    plan: PrimitivePlan,
    *,
    profile: PolicyProfile | str = PolicyProfile.CONSUMER_SAFE,
    imported: bool = False,
    private_or_local: bool = True,
    primitive_registry: PrimitiveRegistry | None = None,
) -> PlanDoctorReport:
    registry = primitive_registry or create_primitive_registry()
    checks: list[DoctorCheck] = [
        DoctorCheck(
            "ok",
            "plan",
            f"compiled {plan.plan_id} with {len(plan.steps)} primitive step(s)",
            section="General",
            details={"plan_id": plan.plan_id},
        )
    ]

    current_os = _current_os()
    for primitive_id in plan.required_primitives:
        try:
            spec = registry.spec(primitive_id)
        except KeyError:
            checks.append(
                DoctorCheck(
                    "error",
                    primitive_id,
                    "primitive is not registered",
                    section="Primitives",
                )
            )
            continue
        if current_os not in spec.supported_platforms:
            checks.append(
                DoctorCheck(
                    "error",
                    primitive_id,
                    "primitive is not supported on "
                    f"{current_os}; supported platforms: {', '.join(spec.supported_platforms)}",
                    section="Primitives",
                    details=spec.to_dict(),
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "ok",
                    primitive_id,
                    f"primitive is supported on {current_os}",
                    section="Primitives",
                    details=spec.to_dict(),
                )
            )

    for capability in plan.required_capabilities:
        checks.append(_check_capability(capability))

    for question in plan.unresolved_questions:
        status = "error" if question.startswith("missing variable") else "warn"
        checks.append(
            DoctorCheck(
                status,
                "unresolved",
                question,
                section="Variables" if question.startswith("missing variable") else "General",
            )
        )

    for confirmation in plan.confirmations_needed:
        checks.append(
            DoctorCheck(
                "warn",
                "confirmation",
                f"confirmation required: {confirmation}",
                section="Safety",
            )
        )

    policy_report = _policy_report_for_plan(
        plan,
        registry=registry,
        profile=profile,
        imported=imported,
        private_or_local=private_or_local,
    )
    for finding in policy_report.findings:
        if finding.blocked:
            checks.append(
                DoctorCheck(
                    "error",
                    finding.primitive_id,
                    finding.reason,
                    section="Policy",
                    details=finding.to_dict(),
                )
            )
        elif finding.disclosure_required:
            checks.append(
                DoctorCheck(
                    "warn",
                    finding.primitive_id,
                    finding.reason,
                    section="Policy",
                    details=finding.to_dict(),
                )
            )

    compatibility = "incompatible" if any(check.status == "error" for check in checks) else (
        "compatible_with_warnings" if any(check.status == "warn" for check in checks) else "compatible"
    )
    return PlanDoctorReport(
        plan_id=plan.plan_id,
        compatibility=compatibility,
        checks=tuple(checks),
        policy_report=policy_report,
    )


def plan_preview_payload(plan: PrimitivePlan, doctor: PlanDoctorReport) -> dict[str, object]:
    return {
        "schema_version": PLAN_PREVIEW_SCHEMA_VERSION,
        "plan": plan.to_dict(),
        "doctor": doctor.to_dict(),
    }


def _compile_diagnostics_intent(
    intent: IntentSpec,
    *,
    registry: PrimitiveRegistry,
    steps: list[PrimitivePlanStep],
    artifacts: list[str],
    verification: list[str],
) -> None:
    preset = str(
        intent.constraints.get("preset")
        or intent.preferences.get("preset")
        or "minimal"
    ).replace("-", "_")
    primitive_id = {
        "minimal": "diagnostics.bundle.collect_minimal",
        "support": "diagnostics.bundle.collect_support",
        "gamer_crash": "diagnostics.bundle.collect_gamer_crash",
    }.get(preset)
    if primitive_id is None:
        primitive_id = "diagnostics.bundle.collect_minimal"
    _append_step(
        steps,
        primitive_id,
        registry=registry,
        step_name=f"Collect {preset.replace('_', '-')} diagnostics",
        parameters={"preset": preset},
    )
    artifacts.extend(["JSON report", "text summary", "zip bundle", "checksums", "redaction summary"])
    verification.append("Verify diagnostics manifest and redaction summary are present.")


def _compile_workspace_intent(
    intent: IntentSpec,
    *,
    registry: PrimitiveRegistry,
    steps: list[PrimitivePlanStep],
    unresolved: list[str],
) -> None:
    target = intent.target if isinstance(intent.target, dict) else {}
    apps = _list_of_mappings(target.get("apps") or target.get("applications"))
    windows = _list_of_mappings(target.get("windows"))
    if not apps and not windows:
        unresolved.append(f"{intent.kind} requires target.apps and/or target.windows")
        return
    for app_index, app in enumerate(apps, start=1):
        command = str(app.get("command") or app.get("path") or "").strip()
        if not command:
            unresolved.append(f"target app {app_index} requires command or path")
            continue
        _append_budgeted_step(
            steps,
            "app.process.launch",
            intent,
            registry=registry,
            unresolved=unresolved,
            step_name=str(app.get("name") or f"Launch app {app_index}"),
            parameters={
                "command": command,
                **({"args": list(app["args"])} if isinstance(app.get("args"), list) else {}),
            },
        )
    for window_index, window in enumerate(windows, start=1):
        matcher = {
            key: value
            for key, value in {
                "title_contains": window.get("title_contains"),
                "process_name": window.get("process_name"),
            }.items()
            if isinstance(value, str) and value.strip()
        }
        if not matcher:
            unresolved.append(f"target window {window_index} requires title_contains or process_name")
            continue
        _append_budgeted_step(
            steps,
            "window.topology.wait",
            intent,
            registry=registry,
            unresolved=unresolved,
            step_name=str(window.get("name") or f"Wait for window {window_index}"),
            parameters={**matcher, "timeout_seconds": window.get("timeout_seconds", 30)},
        )
        if window.get("focus") is True:
            _append_budgeted_step(
                steps,
                "window.topology.focus",
                intent,
                registry=registry,
                unresolved=unresolved,
                step_name=str(window.get("focus_name") or f"Focus window {window_index}"),
                parameters=matcher,
            )
        if window.get("minimize") is True:
            _append_budgeted_step(
                steps,
                "window.topology.minimize",
                intent,
                registry=registry,
                unresolved=unresolved,
                step_name=str(window.get("minimize_name") or f"Minimize window {window_index}"),
                parameters=matcher,
            )


def _append_budgeted_step(
    steps: list[PrimitivePlanStep],
    primitive_id: str,
    intent: IntentSpec,
    *,
    registry: PrimitiveRegistry,
    unresolved: list[str],
    step_name: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    try:
        spec = registry.spec(primitive_id)
    except KeyError:
        unresolved.append(f"primitive {primitive_id} is not registered")
        return
    budget = PrimitiveRisk(intent.risk_budget)
    if _RISK_ORDER[spec.risk] > _RISK_ORDER[budget]:
        unresolved.append(
            f"risk_budget {budget.value} does not allow {primitive_id} ({spec.risk.value})"
        )
        return
    steps.append(
        PrimitivePlanStep(
            primitive_id=primitive_id,
            action_name=spec.action_name,
            step_name=step_name,
            parameters=_redact_mapping(parameters or {}),
            risk=spec.risk,
        )
    )


def _append_step(
    steps: list[PrimitivePlanStep],
    primitive_id: str,
    *,
    registry: PrimitiveRegistry,
    step_name: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    spec = registry.spec(primitive_id)
    steps.append(
        PrimitivePlanStep(
            primitive_id=primitive_id,
            action_name=spec.action_name,
            step_name=step_name,
            parameters=_redact_mapping(parameters or {}),
            risk=spec.risk,
        )
    )


def _finalize_plan(
    plan_id: str,
    *,
    intent: IntentSpec,
    steps: list[PrimitivePlanStep],
    registry: PrimitiveRegistry,
    artifacts_expected: list[str] | tuple[str, ...] = (),
    verification_steps: str | list[str] | tuple[str, ...] = (),
    rollback_or_cleanup_notes: list[str] | tuple[str, ...] = (),
    unresolved_questions: list[str] | tuple[str, ...] = (),
    recipe_id: str | None = None,
) -> PrimitivePlan:
    required_primitives = tuple(dict.fromkeys(step.primitive_id for step in steps))
    capabilities: list[str] = []
    confirmations: list[str] = []
    risk_counts: Counter[str] = Counter()
    for step in steps:
        spec = registry.spec(step.primitive_id)
        risk_counts[spec.risk.value] += 1
        for capability in spec.required_capabilities:
            if capability.value not in capabilities:
                capabilities.append(capability.value)
        if spec.confirmation_policy != "never":
            confirmations.append(
                f"{step.step_name or step.primitive_id}: {spec.confirmation_policy}"
            )
    verification_rows = [verification_steps] if isinstance(verification_steps, str) else list(verification_steps)
    return PrimitivePlan(
        plan_id=plan_id,
        recipe_id=recipe_id,
        steps=tuple(steps),
        intent=intent.to_plan_intent(),
        required_primitives=required_primitives,
        required_capabilities=tuple(capabilities),
        risk_summary=dict(sorted(risk_counts.items())),
        confirmations_needed=tuple(confirmations),
        artifacts_expected=tuple(artifacts_expected),
        verification_steps=tuple(row for row in verification_rows if row),
        rollback_or_cleanup_notes=tuple(rollback_or_cleanup_notes),
        unresolved_questions=tuple(unresolved_questions),
    )


def _policy_report_for_plan(
    plan: PrimitivePlan,
    *,
    registry: PrimitiveRegistry,
    profile: PolicyProfile | str,
    imported: bool,
    private_or_local: bool,
) -> PolicyReport:
    requirements: list[PrimitiveRequirement] = []
    for index, step in enumerate(plan.steps):
        spec = registry.spec(step.primitive_id)
        requirements.append(
            PrimitiveRequirement(
                primitive_id=spec.primitive_id,
                source=f"plan_steps[{index}]",
                action_name=step.action_name,
                spec=spec,
                risk=spec.risk,
                details=step.parameters,
            )
        )
    return PrimitivePolicyEngine(profile=profile, primitive_registry=registry).check_requirements(
        requirements,
        target=plan.plan_id,
        imported=imported,
        private_or_local=private_or_local,
    )


def _step_parameters(step: Any) -> dict[str, Any]:
    if hasattr(step, "model_dump"):
        raw = step.model_dump(mode="json", by_alias=True)
    else:
        raw = dict(getattr(step, "__dict__", {}))
    for key in ("action", "name", "optional", "when"):
        raw.pop(key, None)
    return _redact_mapping({key: value for key, value in raw.items() if value not in (None, "", [], {})})


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RecipeValidationError(f"could not read plan target '{path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise RecipeValidationError(f"invalid YAML in '{path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise RecipeValidationError("plan target must be a YAML mapping")
    return raw


def _resolve_recipe_reference_no_create(recipe_id_or_path: str | Path) -> Path:
    raw = Path(recipe_id_or_path).expanduser()
    if raw.exists() or _looks_like_path_reference(str(recipe_id_or_path)):
        return raw

    recipe_id = str(recipe_id_or_path)
    if not SAFE_ID_PATTERN.fullmatch(recipe_id):
        raise RecipeValidationError(
            "recipe id must be a safe filename-like identifier or a path to a YAML file"
        )
    candidate = recipes_path() / f"{recipe_id}.yaml"
    if not candidate.exists():
        raise RecipeValidationError(f"recipe not found: {recipe_id}")
    return candidate


def _load_recipe_raw_for_plan(raw: dict[str, Any]) -> tuple[Recipe, list[str]]:
    variables = dict(raw.get("variables") or {})
    missing = sorted(_missing_template_variables_for_plan(raw, variables))
    if not missing:
        return load_recipe_document(raw), []

    diagnostic_variables = deepcopy(variables)
    for name in missing:
        _set_missing_variable_for_plan(diagnostic_variables, name, f"__MISSING_{name}__")
    diagnostic_raw = dict(raw)
    diagnostic_raw["variables"] = diagnostic_variables
    return load_recipe_document(diagnostic_raw), missing


def _missing_template_variables_for_plan(
    raw: dict[str, Any],
    variables: dict[str, Any],
) -> set[str]:
    variable_names = collect_template_variables(
        {key: value for key, value in raw.items() if key != "variables"}
    )
    return {name for name in variable_names if not _has_variable_for_plan(name, variables)}


def _has_variable_for_plan(name: str, variables: dict[str, Any]) -> bool:
    current: Any = variables
    for part in name.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return False
    return True


def _set_missing_variable_for_plan(variables: dict[str, Any], name: str, value: str) -> None:
    current = variables
    parts = name.split(".")
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def _looks_like_intent(raw: dict[str, Any]) -> bool:
    return "intent_id" in raw or ("kind" in raw and "steps" not in raw)


def _looks_like_path_reference(value: str) -> bool:
    raw = Path(value)
    return raw.suffix in {".yaml", ".yml"} or raw.parent != Path(".")


def _intent_from_mapping(raw: dict[str, Any]) -> IntentSpec:
    try:
        return IntentSpec.model_validate(raw)
    except ValidationError as exc:
        raise RitualistError(str(exc)) from exc


def _intent_from_kind(kind: str) -> IntentSpec:
    cleaned = kind.strip()
    if not cleaned:
        raise RitualistError("intent kind must not be blank")
    intent_id = cleaned.replace(".", "_").replace("-", "_")
    if not SAFE_ID_PATTERN.fullmatch(intent_id):
        intent_id = "intent_preview"
    return IntentSpec(
        intent_id=intent_id,
        kind=cleaned,
        display_name=cleaned,
        requested_outcome=f"Preview deterministic plan for {cleaned}.",
        user_visible_summary=f"Preview deterministic plan for {cleaned}.",
    )


def _list_of_mappings(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact_mapping(item)
        return redacted
    if isinstance(value, list):
        return [_redact_mapping(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold()
    return any(marker in normalized for marker in ("password", "passwd", "secret", "token", "api_key"))


def _current_os() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform
