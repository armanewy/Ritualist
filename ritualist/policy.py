from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .actions.registry import ActionRegistry, create_default_registry
from .models import Condition, FlowIfStep, Recipe
from .primitives import PrimitiveRegistry, PrimitiveRisk, PrimitiveSpec, create_primitive_registry
from .recipe_loader import load_recipe_for_diagnostics


POLICY_SCHEMA_VERSION = "primitive.policy.v1"


class PolicyCategory(StrEnum):
    IMPORTABLE_WITHOUT_WARNING = "importable_without_warning"
    IMPORTABLE_WITH_DISCLOSURE = "importable_with_disclosure"
    BLOCKED_BY_DEFAULT = "blocked_by_default"
    PRIVATE_PACK_ONLY = "private_pack_only"
    NEVER_IMPORTABLE = "never_importable"


class PolicyDecision(StrEnum):
    ALLOWED = "allowed"
    REQUIRES_DISCLOSURE = "requires_disclosure"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    REQUIRES_DOUBLE_CONFIRMATION = "requires_double_confirmation"
    BLOCKED = "blocked"
    BLOCKED_UNLESS_PRIVATE = "blocked_unless_private"
    BLOCKED_UNLESS_MANAGED = "blocked_unless_managed"


class PolicyProfile(StrEnum):
    CONSUMER_SAFE = "consumer_safe"
    POWER_USER = "power_user"
    LAB_ONLY = "lab_only"
    ENTERPRISE_MANAGED = "enterprise_managed"


NEVER_IMPORTABLE_CLASSES: tuple[str, ...] = (
    "embedded_credentials",
    "arbitrary_unsigned_executables_launched_elevated",
    "opaque_binary_helper_dlls",
    "unsupported_flash_tools",
    "raw_firmware_payloads",
    "force_bios_downgrade",
    "delete_all_restore_points",
    "force_registry_cleanup",
    "destructive_storage_actions_without_local_author_approval",
)

_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
)
_OPAQUE_BINARY_EXTENSIONS = frozenset({".dll", ".sys", ".efi", ".exe", ".msi"})
_FIRMWARE_EXTENSIONS = frozenset({".bin", ".rom", ".cap", ".fd", ".bio"})
_FLASH_TOOL_NAMES = frozenset(
    {
        "afudos",
        "afuwin",
        "atiflash",
        "amdvbflash",
        "nvflash",
        "flashrom",
        "fpt",
    }
)
_DESTRUCTIVE_COMMAND_NAMES = frozenset(
    {
        "diskpart",
        "format",
        "cleanmgr",
        "vssadmin",
        "wmic",
        "bcdedit",
        "reg",
    }
)
_ELEVATION_KEYS = frozenset({"elevated", "run_as_admin", "run_as_administrator", "as_admin"})


@dataclass(frozen=True)
class PrimitiveRequirement:
    primitive_id: str
    source: str
    action_name: str | None = None
    predicate_type: str | None = None
    spec: PrimitiveSpec | None = None
    risk: PrimitiveRisk = PrimitiveRisk.READ_ONLY
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "primitive_id": self.primitive_id,
            "source": self.source,
            "action_name": self.action_name,
            "predicate_type": self.predicate_type,
            "risk": self.risk.value,
            "details": self.details or {},
        }


@dataclass(frozen=True)
class PolicyFinding:
    primitive_id: str
    category: PolicyCategory
    decision: PolicyDecision
    reason: str
    source: str = ""
    action_name: str | None = None
    predicate_type: str | None = None
    risk: PrimitiveRisk = PrimitiveRisk.READ_ONLY
    profile: PolicyProfile = PolicyProfile.CONSUMER_SAFE
    details: dict[str, Any] | None = None

    @property
    def blocked(self) -> bool:
        return self.decision in {
            PolicyDecision.BLOCKED,
            PolicyDecision.BLOCKED_UNLESS_PRIVATE,
            PolicyDecision.BLOCKED_UNLESS_MANAGED,
        }

    @property
    def disclosure_required(self) -> bool:
        return self.decision in {
            PolicyDecision.REQUIRES_DISCLOSURE,
            PolicyDecision.REQUIRES_CONFIRMATION,
            PolicyDecision.REQUIRES_DOUBLE_CONFIRMATION,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "primitive_id": self.primitive_id,
            "category": self.category.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "source": self.source,
            "action_name": self.action_name,
            "predicate_type": self.predicate_type,
            "risk": self.risk.value,
            "profile": self.profile.value,
            "blocked": self.blocked,
            "disclosure_required": self.disclosure_required,
            "details": self.details or {},
        }


@dataclass(frozen=True)
class PolicyReport:
    target: str
    profile: PolicyProfile
    imported: bool
    private_or_local: bool
    managed_policy: bool
    findings: tuple[PolicyFinding, ...]
    schema_version: str = POLICY_SCHEMA_VERSION

    @property
    def blocked_findings(self) -> tuple[PolicyFinding, ...]:
        return tuple(finding for finding in self.findings if finding.blocked)

    @property
    def disclosure_findings(self) -> tuple[PolicyFinding, ...]:
        return tuple(finding for finding in self.findings if finding.disclosure_required)

    @property
    def allowed(self) -> bool:
        return not self.blocked_findings

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target": self.target,
            "profile": self.profile.value,
            "imported": self.imported,
            "private_or_local": self.private_or_local,
            "managed_policy": self.managed_policy,
            "allowed": self.allowed,
            "blocked_count": len(self.blocked_findings),
            "disclosure_count": len(self.disclosure_findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def policy_overview() -> dict[str, object]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "default_profile": PolicyProfile.CONSUMER_SAFE.value,
        "categories": [category.value for category in PolicyCategory],
        "decisions": [decision.value for decision in PolicyDecision],
        "profiles": {
            PolicyProfile.CONSUMER_SAFE.value: "Prefer importable read-only/runbook actions; block risky primitives.",
            PolicyProfile.POWER_USER.value: "Allow local/private risky primitives with explicit confirmation.",
            PolicyProfile.LAB_ONLY.value: "Allow local/private risky primitives with double confirmation.",
            PolicyProfile.ENTERPRISE_MANAGED.value: "Allow risky primitives only when a managed policy flag is present.",
        },
        "risk_defaults": {
            PrimitiveRisk.READ_ONLY.value: PolicyCategory.IMPORTABLE_WITHOUT_WARNING.value,
            PrimitiveRisk.LAUNCHES_APP.value: PolicyCategory.IMPORTABLE_WITHOUT_WARNING.value,
            PrimitiveRisk.CONTROLS_UI.value: PolicyCategory.IMPORTABLE_WITHOUT_WARNING.value,
            PrimitiveRisk.MODIFIES_FILES.value: PolicyCategory.IMPORTABLE_WITH_DISCLOSURE.value,
            PrimitiveRisk.RISKY.value: PolicyCategory.BLOCKED_BY_DEFAULT.value,
        },
        "never_importable_classes": list(NEVER_IMPORTABLE_CLASSES),
    }


class PrimitivePolicyEngine:
    def __init__(
        self,
        *,
        profile: PolicyProfile | str = PolicyProfile.CONSUMER_SAFE,
        primitive_registry: PrimitiveRegistry | None = None,
    ) -> None:
        self.profile = _coerce_profile(profile)
        self.primitive_registry = primitive_registry or create_primitive_registry()

    def check_requirements(
        self,
        requirements: Iterable[PrimitiveRequirement],
        *,
        target: str,
        imported: bool,
        private_or_local: bool = False,
        managed_policy: bool = False,
    ) -> PolicyReport:
        findings = tuple(
            self.evaluate_requirement(
                requirement,
                imported=imported,
                private_or_local=private_or_local,
                managed_policy=managed_policy,
            )
            for requirement in requirements
        )
        return PolicyReport(
            target=target,
            profile=self.profile,
            imported=imported,
            private_or_local=private_or_local,
            managed_policy=managed_policy,
            findings=findings,
        )

    def evaluate_requirement(
        self,
        requirement: PrimitiveRequirement,
        *,
        imported: bool,
        private_or_local: bool = False,
        managed_policy: bool = False,
    ) -> PolicyFinding:
        spec = requirement.spec
        if spec is None:
            try:
                spec = self.primitive_registry.spec(requirement.primitive_id)
            except KeyError:
                return PolicyFinding(
                    primitive_id=requirement.primitive_id,
                    category=PolicyCategory.BLOCKED_BY_DEFAULT,
                    decision=PolicyDecision.BLOCKED,
                    reason="primitive is not registered",
                    source=requirement.source,
                    action_name=requirement.action_name,
                    predicate_type=requirement.predicate_type,
                    risk=requirement.risk,
                    profile=self.profile,
                    details=requirement.details,
                )

        category = _policy_category_for(spec, requirement.details or {}, profile=self.profile)
        decision = _decision_for_category(
            category,
            profile=self.profile,
            imported=imported,
            private_or_local=private_or_local,
            managed_policy=managed_policy,
        )
        return PolicyFinding(
            primitive_id=spec.primitive_id,
            category=category,
            decision=decision,
            reason=_reason_for_decision(category, decision, spec, requirement.details or {}),
            source=requirement.source,
            action_name=requirement.action_name,
            predicate_type=requirement.predicate_type,
            risk=spec.risk,
            profile=self.profile,
            details=requirement.details,
        )


def explain_primitive_policy(
    primitive_id: str,
    *,
    profile: PolicyProfile | str = PolicyProfile.CONSUMER_SAFE,
    imported: bool = True,
    private_or_local: bool = False,
    managed_policy: bool = False,
    registry: ActionRegistry | None = None,
) -> PolicyFinding:
    primitive_registry = create_primitive_registry(registry)
    spec = primitive_registry.spec(primitive_id)
    return PrimitivePolicyEngine(
        profile=profile,
        primitive_registry=primitive_registry,
    ).evaluate_requirement(
        PrimitiveRequirement(
            primitive_id=spec.primitive_id,
            source="primitive",
            action_name=spec.action_name,
            spec=spec,
            risk=spec.risk,
        ),
        imported=imported,
        private_or_local=private_or_local,
        managed_policy=managed_policy,
    )


def build_policy_report_for_recipe(
    recipe: Recipe,
    *,
    target: str | None = None,
    profile: PolicyProfile | str = PolicyProfile.CONSUMER_SAFE,
    imported: bool = False,
    private_or_local: bool = True,
    managed_policy: bool = False,
    registry: ActionRegistry | None = None,
) -> PolicyReport:
    action_registry = registry or create_default_registry()
    primitive_registry = create_primitive_registry(action_registry)
    requirements = collect_recipe_primitive_requirements(
        recipe,
        primitive_registry=primitive_registry,
    )
    return PrimitivePolicyEngine(
        profile=profile,
        primitive_registry=primitive_registry,
    ).check_requirements(
        requirements,
        target=target or recipe.id,
        imported=imported,
        private_or_local=private_or_local,
        managed_policy=managed_policy,
    )


def build_policy_report_for_recipe_reference(
    recipe_id_or_path: str | Path,
    *,
    profile: PolicyProfile | str = PolicyProfile.CONSUMER_SAFE,
    registry: ActionRegistry | None = None,
) -> PolicyReport:
    recipe, _raw, _missing = load_recipe_for_diagnostics(recipe_id_or_path)
    return build_policy_report_for_recipe(
        recipe,
        target=str(recipe_id_or_path),
        profile=profile,
        imported=False,
        private_or_local=True,
        managed_policy=False,
        registry=registry,
    )


def collect_recipe_primitive_requirements(
    recipe: Recipe,
    *,
    primitive_registry: PrimitiveRegistry | None = None,
) -> tuple[PrimitiveRequirement, ...]:
    registry = primitive_registry or create_primitive_registry()
    requirements: list[PrimitiveRequirement] = []
    requirements.extend(_collect_steps(recipe.preflight, section="preflight", registry=registry))
    requirements.extend(_collect_steps(recipe.steps, section="steps", registry=registry))
    requirements.extend(_collect_steps(recipe.verify, section="verify", registry=registry))
    return tuple(requirements)


def detect_never_importable_raw(
    recipe_raw: Mapping[str, Any],
    *,
    manifest_raw: Mapping[str, Any] | None = None,
    asset_names: Iterable[str] = (),
) -> tuple[PolicyFinding, ...]:
    findings: list[PolicyFinding] = []
    for path, key, value in _walk_mapping_values(
        {"recipe": recipe_raw, "manifest": manifest_raw or {}}
    ):
        normalized_key = str(key).casefold().replace("-", "_")
        if _is_secret_key(normalized_key) and _is_concrete_secret(value):
            findings.append(
                _never_importable_finding(
                    "embedded_credentials",
                    f"{path}.{key}",
                    "embedded credential-like values are never importable from packs",
                )
            )
        if normalized_key in _ELEVATION_KEYS and value is True:
            findings.append(
                _never_importable_finding(
                    "arbitrary_unsigned_executables_launched_elevated",
                    f"{path}.{key}",
                    "elevated unsigned executable launch requests are never importable",
                )
            )
        if isinstance(value, str):
            findings.extend(_dangerous_text_findings(value, f"{path}.{key}"))

    for asset_name in asset_names:
        suffix = Path(asset_name).suffix.casefold()
        stem = Path(asset_name).stem.casefold()
        if suffix in _OPAQUE_BINARY_EXTENSIONS:
            findings.append(
                _never_importable_finding(
                    "opaque_binary_helper_dlls",
                    f"asset:{asset_name}",
                    "opaque executable or helper binary assets are never importable",
                )
            )
        if suffix in _FIRMWARE_EXTENSIONS:
            findings.append(
                _never_importable_finding(
                    "raw_firmware_payloads",
                    f"asset:{asset_name}",
                    "raw firmware payload assets are never importable",
                )
            )
        if stem in _FLASH_TOOL_NAMES:
            findings.append(
                _never_importable_finding(
                    "unsupported_flash_tools",
                    f"asset:{asset_name}",
                    "unsupported flash tools are never importable",
                )
            )
    return tuple(_dedupe_findings(findings))


def blocked_policy_messages(report: PolicyReport) -> list[str]:
    return [
        f"{finding.primitive_id} at {finding.source}: {finding.reason}"
        for finding in report.blocked_findings
    ]


def _collect_steps(
    steps: Iterable[Any],
    *,
    section: str,
    registry: PrimitiveRegistry,
) -> list[PrimitiveRequirement]:
    requirements: list[PrimitiveRequirement] = []
    for index, step in enumerate(steps):
        source = f"{section}[{index}]"
        requirements.append(_requirement_for_action(step, source=source, registry=registry))
        when = getattr(step, "when", None)
        if when is not None:
            requirements.extend(_collect_condition(when, source=f"{source}.when", registry=registry))
        if isinstance(step, FlowIfStep):
            requirements.extend(
                _collect_condition(step.condition, source=f"{source}.condition", registry=registry)
            )
            requirements.extend(_collect_steps(step.then, section=f"{source}.then", registry=registry))
            requirements.extend(_collect_steps(step.else_, section=f"{source}.else", registry=registry))
        timeout_steps = getattr(step, "on_timeout", None) or []
        requirements.extend(
            _collect_steps(timeout_steps, section=f"{source}.on_timeout", registry=registry)
        )
    return requirements


def _requirement_for_action(
    step: Any,
    *,
    source: str,
    registry: PrimitiveRegistry,
) -> PrimitiveRequirement:
    action_name = getattr(step, "action", "")
    try:
        spec = registry.spec_for_action(action_name)
    except KeyError:
        return PrimitiveRequirement(
            primitive_id=f"unknown.{action_name or 'action'}",
            action_name=action_name,
            source=source,
            details=_step_details(step),
        )
    return PrimitiveRequirement(
        primitive_id=spec.primitive_id,
        action_name=action_name,
        source=source,
        spec=spec,
        risk=spec.risk,
        details=_step_details(step),
    )


def _collect_condition(
    condition: Condition,
    *,
    source: str,
    registry: PrimitiveRegistry,
) -> list[PrimitiveRequirement]:
    requirements: list[PrimitiveRequirement] = []
    if condition.all is not None:
        for index, child in enumerate(condition.all):
            requirements.extend(
                _collect_condition(child, source=f"{source}.all[{index}]", registry=registry)
            )
        return requirements
    if condition.any is not None:
        for index, child in enumerate(condition.any):
            requirements.extend(
                _collect_condition(child, source=f"{source}.any[{index}]", registry=registry)
            )
        return requirements
    if condition.not_ is not None:
        return _collect_condition(condition.not_, source=f"{source}.not", registry=registry)
    if condition.type is None:
        return requirements
    primitive_id = _primitive_id_for_predicate(condition.type)
    spec = _optional_registry_spec(registry, primitive_id)
    requirements.append(
        PrimitiveRequirement(
            primitive_id=primitive_id,
            predicate_type=condition.type,
            source=source,
            spec=spec,
            risk=spec.risk if spec else PrimitiveRisk.READ_ONLY,
            details={"predicate_type": condition.type},
        )
    )
    return requirements


def _primitive_id_for_predicate(predicate_type: str) -> str:
    return {
        "file.exists": "filesystem.assert.file_exists",
        "path.exists": "filesystem.assert.path_exists",
        "process.running": "app.process.is_running",
        "window.exists": "window.topology.exists",
        "window.text_visible": "uia.element.text_visible",
        "browser.text_visible": "browser.assert.text_visible",
    }[predicate_type]


def _optional_registry_spec(registry: PrimitiveRegistry, primitive_id: str) -> PrimitiveSpec | None:
    try:
        return registry.spec(primitive_id)
    except KeyError:
        return None


def _policy_category_for(
    spec: PrimitiveSpec,
    details: Mapping[str, Any],
    *,
    profile: PolicyProfile,
) -> PolicyCategory:
    if spec.risk is PrimitiveRisk.READ_ONLY:
        return PolicyCategory.IMPORTABLE_WITHOUT_WARNING
    if spec.risk is PrimitiveRisk.MODIFIES_FILES:
        return PolicyCategory.IMPORTABLE_WITH_DISCLOSURE
    if spec.risk is PrimitiveRisk.LAUNCHES_APP:
        if _launch_requires_disclosure(spec, details):
            return PolicyCategory.IMPORTABLE_WITH_DISCLOSURE
        return PolicyCategory.IMPORTABLE_WITHOUT_WARNING
    if spec.risk is PrimitiveRisk.CONTROLS_UI:
        if _controls_ui_requires_disclosure(spec, details):
            return PolicyCategory.IMPORTABLE_WITH_DISCLOSURE
        return PolicyCategory.IMPORTABLE_WITHOUT_WARNING
    if spec.risk is PrimitiveRisk.RISKY:
        if profile in {PolicyProfile.POWER_USER, PolicyProfile.LAB_ONLY}:
            return PolicyCategory.PRIVATE_PACK_ONLY
        return PolicyCategory.BLOCKED_BY_DEFAULT
    return PolicyCategory.BLOCKED_BY_DEFAULT


def _decision_for_category(
    category: PolicyCategory,
    *,
    profile: PolicyProfile,
    imported: bool,
    private_or_local: bool,
    managed_policy: bool,
) -> PolicyDecision:
    if category is PolicyCategory.NEVER_IMPORTABLE:
        return PolicyDecision.BLOCKED
    if category is PolicyCategory.IMPORTABLE_WITHOUT_WARNING:
        return PolicyDecision.ALLOWED
    if category is PolicyCategory.IMPORTABLE_WITH_DISCLOSURE:
        return PolicyDecision.REQUIRES_DISCLOSURE
    if category is PolicyCategory.BLOCKED_BY_DEFAULT:
        if profile is PolicyProfile.ENTERPRISE_MANAGED:
            return (
                PolicyDecision.REQUIRES_DOUBLE_CONFIRMATION
                if managed_policy
                else PolicyDecision.BLOCKED_UNLESS_MANAGED
            )
        return PolicyDecision.BLOCKED
    if category is PolicyCategory.PRIVATE_PACK_ONLY:
        if private_or_local:
            if profile is PolicyProfile.LAB_ONLY:
                return PolicyDecision.REQUIRES_DOUBLE_CONFIRMATION
            return PolicyDecision.REQUIRES_CONFIRMATION
        return PolicyDecision.BLOCKED_UNLESS_PRIVATE
    return PolicyDecision.BLOCKED


def _reason_for_decision(
    category: PolicyCategory,
    decision: PolicyDecision,
    spec: PrimitiveSpec,
    details: Mapping[str, Any],
) -> str:
    if decision is PolicyDecision.ALLOWED:
        return f"{spec.risk.value} primitive is importable under the selected profile"
    if decision is PolicyDecision.REQUIRES_DISCLOSURE:
        return _disclosure_reason(spec, details)
    if decision is PolicyDecision.REQUIRES_CONFIRMATION:
        return "risky primitive is allowed only for local/private use with confirmation"
    if decision is PolicyDecision.REQUIRES_DOUBLE_CONFIRMATION:
        return "risky primitive requires explicit double confirmation under this profile"
    if decision is PolicyDecision.BLOCKED_UNLESS_PRIVATE:
        return "risky primitive is blocked for untrusted imported packs"
    if decision is PolicyDecision.BLOCKED_UNLESS_MANAGED:
        return "primitive is blocked unless managed policy permits it"
    if category is PolicyCategory.NEVER_IMPORTABLE:
        return "primitive class is never importable from untrusted packs"
    return f"{spec.risk.value} primitive is blocked by default"


def _disclosure_reason(spec: PrimitiveSpec, details: Mapping[str, Any]) -> str:
    if spec.action_name == "app.launch":
        command = str(details.get("command", "")).strip()
        if command:
            return f"launches local app path or command and requires disclosure: {command}"
    if spec.risk is PrimitiveRisk.CONTROLS_UI:
        return "controls existing UI and requires disclosure in imported packs"
    if spec.risk is PrimitiveRisk.MODIFIES_FILES:
        return "modifies local files and requires disclosure"
    return "requires disclosure before import/enable"


def _launch_requires_disclosure(spec: PrimitiveSpec, details: Mapping[str, Any]) -> bool:
    if spec.action_name != "app.launch":
        return False
    command = str(details.get("command", "")).strip()
    if not command or "{{" in command:
        return False
    path = Path(command)
    return path.is_absolute() or path.suffix.casefold() in {".exe", ".app", ".bat", ".cmd"}


def _controls_ui_requires_disclosure(spec: PrimitiveSpec, details: Mapping[str, Any]) -> bool:
    return spec.action_name in {
        "browser.media",
        "window.focus",
        "window.minimize",
        "window.move",
        "window.resize",
        "window.maximize",
        "window.restore",
        "window.snap_left",
        "window.snap_right",
        "window.snap_top",
        "window.snap_bottom",
    }


def _step_details(step: Any) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for name in (
        "command",
        "args",
        "cwd",
        "text",
        "window_title_contains",
        "title_contains",
        "process_name",
        "path",
        "url",
        "role",
        "accessible_name",
        "test_id",
    ):
        if hasattr(step, name):
            value = getattr(step, name)
            if value not in (None, "", [], {}):
                details[name] = value
    return details


def _coerce_profile(profile: PolicyProfile | str) -> PolicyProfile:
    if isinstance(profile, PolicyProfile):
        return profile
    return PolicyProfile(str(profile))


def _walk_mapping_values(source: object, *, path: str = "") -> Iterable[tuple[str, str, object]]:
    if isinstance(source, Mapping):
        for key, value in source.items():
            current_path = f"{path}.{key}" if path else str(key)
            yield path or "root", str(key), value
            yield from _walk_mapping_values(value, path=current_path)
    elif isinstance(source, list):
        for index, item in enumerate(source):
            yield from _walk_mapping_values(item, path=f"{path}[{index}]")


def _is_secret_key(key: str) -> bool:
    return any(part in key for part in _SECRET_KEY_PARTS)


def _is_concrete_secret(value: object) -> bool:
    if not isinstance(value, str | int | float | bool):
        return False
    text = str(value).strip()
    if not text or "{{" in text or "}}" in text:
        return False
    if text.startswith("__MISSING_") or text.startswith("__REQUIRED_"):
        return False
    return True


def _dangerous_text_findings(text: str, source: str) -> list[PolicyFinding]:
    normalized = " ".join(text.casefold().replace("\\", "/").split())
    findings: list[PolicyFinding] = []
    command_name = Path(normalized.split(" ", 1)[0]).stem if normalized else ""
    if command_name in _FLASH_TOOL_NAMES or "bios downgrade" in normalized:
        findings.append(
            _never_importable_finding(
                "unsupported_flash_tools",
                source,
                "unsupported flash tooling or BIOS downgrade command is never importable",
            )
        )
    if "delete shadows" in normalized or "shadowcopy delete" in normalized:
        findings.append(
            _never_importable_finding(
                "delete_all_restore_points",
                source,
                "commands that delete restore points are never importable",
            )
        )
    if "registry cleanup" in normalized or ("reg delete" in normalized and "/f" in normalized):
        findings.append(
            _never_importable_finding(
                "force_registry_cleanup",
                source,
                "forced registry cleanup commands are never importable",
            )
        )
    if command_name in _DESTRUCTIVE_COMMAND_NAMES and any(
        token in normalized for token in ("clean", "format", "delete", "downgrade")
    ):
        findings.append(
            _never_importable_finding(
                "destructive_storage_actions_without_local_author_approval",
                source,
                "destructive storage or system cleanup command is never importable",
            )
        )
    return findings


def _never_importable_finding(
    primitive_id: str,
    source: str,
    reason: str,
) -> PolicyFinding:
    return PolicyFinding(
        primitive_id=primitive_id,
        category=PolicyCategory.NEVER_IMPORTABLE,
        decision=PolicyDecision.BLOCKED,
        reason=reason,
        source=source,
        risk=PrimitiveRisk.RISKY,
        profile=PolicyProfile.CONSUMER_SAFE,
    )


def _dedupe_findings(findings: Iterable[PolicyFinding]) -> list[PolicyFinding]:
    deduped: list[PolicyFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding.primitive_id, finding.source, finding.reason)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped
