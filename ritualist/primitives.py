from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol

from .actions.catalog import create_action_catalog
from .actions.metadata import ActionMetadata, CapabilityName, PlatformName
from .actions.registry import ActionRegistry, create_default_registry


_PRIMITIVE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PRIMITIVE_VERB_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


KNOWN_PRIMITIVE_FAMILIES: tuple[str, ...] = (
    "app.process",
    "service.control",
    "window.topology",
    "uia.element",
    "browser.session",
    "browser.interact",
    "browser.assert",
    "hardware.inventory",
    "network.connectivity",
    "diagnostics.bundle",
    "target.resolution",
    "runtime.assert",
    "packages.winget",
    "sandbox.run",
    "obs.session",
    "vendor.update",
    "firmware.guard",
    "firmware.vendor_flash",
)


class PrimitiveRisk(str, Enum):
    READ_ONLY = "read_only"
    LAUNCHES_APP = "launches_app"
    CONTROLS_UI = "controls_ui"
    MODIFIES_FILES = "modifies_files"
    RISKY = "risky"


class PrimitiveCapability(str, Enum):
    PLAYWRIGHT = "playwright"
    WINDOWS_UIA = "windows_uia"
    APP_LAUNCH = "app_launch"
    BROWSER_CONTROL = "browser_control"
    NATIVE_BROWSER_HANDOFF = "native_browser_handoff"
    WINDOW_MANAGEMENT = "window_management"
    KEYBOARD_INPUT = "keyboard_input"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    REGISTRY_READ = "registry_read"
    REGISTRY_WRITE = "registry_write"
    PROCESS_INSPECTION = "process_inspection"
    HARDWARE_INVENTORY = "hardware_inventory"
    NETWORK_CONNECTIVITY = "network_connectivity"
    DIAGNOSTICS_COLLECT = "diagnostics_collect"


@dataclass(frozen=True)
class PrimitiveFamily:
    name: str

    def __post_init__(self) -> None:
        _validate_family(self.name)

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name}


@dataclass(frozen=True)
class PrimitiveVerb:
    name: str

    def __post_init__(self) -> None:
        if not _PRIMITIVE_VERB_PATTERN.fullmatch(self.name):
            raise ValueError("primitive verb must be lowercase snake_case")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name}


@dataclass(frozen=True)
class PrimitiveParameter:
    name: str
    required: bool
    description: str = ""
    sensitive: bool = False

    def __post_init__(self) -> None:
        _require_non_empty_string("parameter name", self.name)
        if not isinstance(self.required, bool):
            raise ValueError("parameter required must be a bool")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PrimitiveAdapterBinding:
    adapter_id: str
    binding_type: str
    description: str = ""

    def __post_init__(self) -> None:
        _require_non_empty_string("adapter_id", self.adapter_id)
        _require_non_empty_string("binding_type", self.binding_type)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PrimitiveVerification:
    name: str
    status: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PrimitiveArtifact:
    artifact_type: str
    name: str
    path: str | None = None
    redacted: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PrimitiveExecutionResult:
    status: str
    message: str = ""
    verification: PrimitiveVerification | None = None
    artifacts: tuple[PrimitiveArtifact, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "verification": self.verification.to_dict() if self.verification else None,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "details": self.details,
        }


@dataclass(frozen=True)
class PrimitiveSpec:
    family: PrimitiveFamily
    verb: PrimitiveVerb
    display_name: str
    description: str
    required_capabilities: tuple[PrimitiveCapability, ...]
    supported_platforms: tuple[PlatformName, ...]
    risk: PrimitiveRisk
    confirmation_policy: str
    allowed_in_imported_packs: bool
    adapter_binding: PrimitiveAdapterBinding
    parameters: tuple[PrimitiveParameter, ...] = ()
    schema_version: str = "primitive.v1"
    action_name: str | None = None
    dry_run_behavior: str = "describe plan step without adapter side effects"
    artifact_behavior: str = "none"
    verification_behavior: str = "result status only"

    @property
    def primitive_id(self) -> str:
        return f"{self.family.name}.{self.verb.name}"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "primitive_id": self.primitive_id,
            "family": self.family.name,
            "verb": self.verb.name,
            "display_name": self.display_name,
            "description": self.description,
            "required_capabilities": [capability.value for capability in self.required_capabilities],
            "supported_platforms": list(self.supported_platforms),
            "risk": self.risk.value,
            "confirmation_policy": self.confirmation_policy,
            "allowed_in_imported_packs": self.allowed_in_imported_packs,
            "adapter_binding": self.adapter_binding.to_dict(),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "action_name": self.action_name,
            "dry_run_behavior": self.dry_run_behavior,
            "artifact_behavior": self.artifact_behavior,
            "verification_behavior": self.verification_behavior,
        }


@dataclass(frozen=True)
class PrimitivePlanStep:
    primitive_id: str
    action_name: str | None = None
    step_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    risk: PrimitiveRisk | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "primitive_id": self.primitive_id,
            "action_name": self.action_name,
            "step_name": self.step_name,
            "parameters": self.parameters,
            "risk": self.risk.value if self.risk else None,
        }


@dataclass(frozen=True)
class PrimitivePlan:
    plan_id: str
    steps: tuple[PrimitivePlanStep, ...]
    recipe_id: str | None = None
    intent: dict[str, Any] | None = None
    required_primitives: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    risk_summary: dict[str, int] = field(default_factory=dict)
    confirmations_needed: tuple[str, ...] = ()
    artifacts_expected: tuple[str, ...] = ()
    verification_steps: tuple[str, ...] = ()
    rollback_or_cleanup_notes: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "recipe_id": self.recipe_id,
            "intent": self.intent,
            "plan_steps": [step.to_dict() for step in self.steps],
            "steps": [step.to_dict() for step in self.steps],
            "required_primitives": list(self.required_primitives),
            "required_capabilities": list(self.required_capabilities),
            "risk_summary": dict(self.risk_summary),
            "confirmations_needed": list(self.confirmations_needed),
            "artifacts_expected": list(self.artifacts_expected),
            "verification_steps": list(self.verification_steps),
            "cleanup_or_rollback_notes": list(self.rollback_or_cleanup_notes),
            "rollback_or_cleanup_notes": list(self.rollback_or_cleanup_notes),
            "unresolved_questions": list(self.unresolved_questions),
        }


class PrimitiveAdapter(Protocol):
    adapter_id: str
    supported_primitives: tuple[str, ...]
    supported_families: tuple[str, ...]
    supported_verbs: tuple[str, ...]

    def capability_probes(self) -> dict[str, bool]: ...

    def doctor_checks(self) -> list[PrimitiveVerification]: ...

    def dry_run(self, plan_step: PrimitivePlanStep) -> PrimitiveExecutionResult: ...

    def execute(self, plan_step: PrimitivePlanStep) -> PrimitiveExecutionResult: ...

    def verify(self, plan_step: PrimitivePlanStep) -> PrimitiveVerification: ...

    def collect_artifacts(self, plan_step: PrimitivePlanStep) -> tuple[PrimitiveArtifact, ...]: ...


@dataclass(frozen=True)
class FakePrimitiveAdapter:
    adapter_id: str = "fake.primitive"
    supported_primitives: tuple[str, ...] = ()
    supported_families: tuple[str, ...] = ()
    supported_verbs: tuple[str, ...] = ()

    def capability_probes(self) -> dict[str, bool]:
        return {}

    def doctor_checks(self) -> list[PrimitiveVerification]:
        return [
            PrimitiveVerification(
                name=self.adapter_id,
                status="ok",
                message="fake primitive adapter available for metadata tests",
            )
        ]

    def dry_run(self, plan_step: PrimitivePlanStep) -> PrimitiveExecutionResult:
        return PrimitiveExecutionResult(
            status="dry-run",
            message=f"would execute primitive {plan_step.primitive_id}",
        )

    def execute(self, plan_step: PrimitivePlanStep) -> PrimitiveExecutionResult:
        return PrimitiveExecutionResult(
            status="skipped",
            message="fake primitive adapter does not execute host side effects",
        )

    def verify(self, plan_step: PrimitivePlanStep) -> PrimitiveVerification:
        return PrimitiveVerification(
            name=plan_step.primitive_id,
            status="ok",
            message="fake verification only",
        )

    def collect_artifacts(self, plan_step: PrimitivePlanStep) -> tuple[PrimitiveArtifact, ...]:
        return ()


@dataclass
class PrimitiveRegistry:
    _specs: dict[str, PrimitiveSpec] = field(default_factory=dict)
    _action_to_primitive: dict[str, str] = field(default_factory=dict)

    def register(self, spec: PrimitiveSpec) -> None:
        primitive_id = spec.primitive_id
        if primitive_id in self._specs:
            raise ValueError(f"duplicate primitive '{primitive_id}'")
        self._specs[primitive_id] = spec
        if spec.action_name:
            self._action_to_primitive[spec.action_name] = primitive_id

    def has(self, primitive_id: str) -> bool:
        return primitive_id in self._specs

    def primitive_ids(self) -> list[str]:
        return sorted(self._specs)

    def specs(self) -> list[PrimitiveSpec]:
        return [self._specs[primitive_id] for primitive_id in self.primitive_ids()]

    def spec(self, primitive_id: str) -> PrimitiveSpec:
        try:
            return self._specs[primitive_id]
        except KeyError as exc:
            raise KeyError(f"no primitive registered for '{primitive_id}'") from exc

    def spec_for_action(self, action_name: str) -> PrimitiveSpec:
        try:
            primitive_id = self._action_to_primitive[action_name]
        except KeyError as exc:
            raise KeyError(f"no primitive registered for action '{action_name}'") from exc
        return self.spec(primitive_id)

    def families(self) -> list[str]:
        return sorted({spec.family.name for spec in self._specs.values()})

    def to_dict(self) -> list[dict[str, object]]:
        return [spec.to_dict() for spec in self.specs()]


def create_primitive_registry(action_registry: ActionRegistry | None = None) -> PrimitiveRegistry:
    resolved_action_registry = action_registry or create_default_registry()
    catalog = create_action_catalog(resolved_action_registry)
    registry = PrimitiveRegistry()
    for metadata in resolved_action_registry.metadata_items():
        catalog_entry = catalog.entry(metadata.action_name)
        registry.register(
            primitive_spec_from_action_metadata(
                metadata,
                display_name=catalog_entry.display_name,
                description=catalog_entry.description,
            )
        )
    _register_read_only_primitives(registry)
    return registry


def read_only_primitive_ids() -> tuple[str, ...]:
    return tuple(spec.primitive_id for spec in _read_only_primitive_specs())


def primitive_spec_from_action_metadata(
    metadata: ActionMetadata,
    *,
    display_name: str | None = None,
    description: str | None = None,
) -> PrimitiveSpec:
    family_name, verb_name = _primitive_mapping(metadata.action_name)
    return PrimitiveSpec(
        family=PrimitiveFamily(family_name),
        verb=PrimitiveVerb(verb_name),
        display_name=display_name or _display_name(metadata.action_name),
        description=description or f"Primitive backing action {metadata.action_name}.",
        required_capabilities=tuple(
            PrimitiveCapability(capability) for capability in metadata.required_capabilities
        ),
        supported_platforms=metadata.supported_platforms,
        risk=risk_from_side_effect_level(metadata.side_effect_level),
        confirmation_policy=metadata.confirmation_policy,
        allowed_in_imported_packs=metadata.allowed_in_imported_packs,
        adapter_binding=_adapter_binding_for(metadata.action_name, family_name),
        parameters=_parameters_from_metadata(metadata),
        action_name=metadata.action_name,
        artifact_behavior=_artifact_behavior(metadata.action_name),
        verification_behavior=_verification_behavior(metadata.action_name),
    )


def build_primitive_plan_for_actions(
    action_names: Iterable[str],
    registry: PrimitiveRegistry | None = None,
    *,
    plan_id: str = "recipe",
    recipe_id: str | None = None,
) -> PrimitivePlan:
    resolved_registry = registry or create_primitive_registry()
    steps: list[PrimitivePlanStep] = []
    for action_name in action_names:
        spec = resolved_registry.spec_for_action(action_name)
        steps.append(
            PrimitivePlanStep(
                primitive_id=spec.primitive_id,
                action_name=action_name,
                risk=spec.risk,
            )
        )
    return PrimitivePlan(plan_id=plan_id, recipe_id=recipe_id, steps=tuple(steps))


def risk_from_side_effect_level(side_effect_level: str) -> PrimitiveRisk:
    if side_effect_level == "types_input":
        return PrimitiveRisk.RISKY
    return PrimitiveRisk(side_effect_level)


def _primitive_mapping(action_name: str) -> tuple[str, str]:
    explicit: dict[str, tuple[str, str]] = {
        "app.launch": ("app.process", "launch"),
        "app.wait_process": ("app.process", "wait_process"),
        "assert.browser_text_visible": ("browser.assert", "text_visible"),
        "assert.file_exists": ("filesystem.assert", "file_exists"),
        "assert.path_exists": ("filesystem.assert", "path_exists"),
        "assert.process_running": ("app.process", "is_running"),
        "assert.registry_value": ("registry.read", "value"),
        "assert.window_exists": ("window.topology", "exists"),
        "assert.window_text_visible": ("uia.element", "text_visible"),
        "browser.click_role": ("browser.interact", "click_role"),
        "browser.click_test_id": ("browser.interact", "click_test_id"),
        "browser.click_text": ("browser.interact", "click_text"),
        "browser.element_visible": ("browser.assert", "element_visible"),
        "browser.media": ("browser.interact", "media"),
        "browser.open": ("browser.session", "open"),
        "browser.open_native": ("browser.session", "open_native"),
        "browser.wait_media_playing": ("browser.assert", "wait_media_playing"),
        "browser.wait_text": ("browser.assert", "wait_text"),
        "browser.wait_title": ("browser.assert", "wait_title"),
        "browser.wait_url": ("browser.assert", "wait_url"),
        "confirm.ask": ("operator.prompt", "confirm"),
        "desktop.click_text": ("uia.element", "click_text"),
        "flow.if": ("flow.control", "if"),
        "human.checklist": ("operator.prompt", "checklist"),
        "human.confirm_evidence": ("operator.prompt", "confirm_evidence"),
        "human.prompt": ("operator.prompt", "prompt"),
        "input.hotkey": ("input.keyboard", "hotkey"),
        "note.add": ("diagnostics.bundle", "note"),
        "notify.beep": ("operator.notify", "beep"),
        "notify.sound": ("operator.notify", "sound"),
        "notify.toast": ("operator.notify", "toast"),
        "target.inspect": ("target.resolution", "inspect"),
        "target.wait_state": ("target.resolution", "wait_state"),
        "wait.for_file": ("filesystem.wait", "for_file"),
        "wait.for_process": ("app.process", "wait_for_process"),
        "wait.for_process_exit": ("app.process", "wait_for_process_exit"),
        "wait.for_user": ("operator.prompt", "wait_user"),
        "wait.for_window": ("window.topology", "wait_for_window"),
        "wait.for_window_gone": ("window.topology", "wait_for_window_gone"),
        "wait.seconds": ("runtime.wait", "seconds"),
        "window.focus": ("window.topology", "focus"),
        "window.maximize": ("window.topology", "maximize"),
        "window.minimize": ("window.topology", "minimize"),
        "window.move": ("window.topology", "move"),
        "window.resize": ("window.topology", "resize"),
        "window.restore": ("window.topology", "restore"),
        "window.snap_bottom": ("window.topology", "snap_bottom"),
        "window.snap_left": ("window.topology", "snap_left"),
        "window.snap_right": ("window.topology", "snap_right"),
        "window.snap_top": ("window.topology", "snap_top"),
        "window.wait": ("window.topology", "wait"),
    }
    try:
        return explicit[action_name]
    except KeyError:
        category, _, verb = action_name.partition(".")
        family = f"{category}.primitive"
        return family, verb or category


def _adapter_binding_for(action_name: str, family_name: str) -> PrimitiveAdapterBinding:
    if action_name == "browser.open_native":
        return PrimitiveAdapterBinding(
            "native_browser",
            "os_default_browser",
            "OS default browser handoff",
        )
    if action_name.startswith("browser.") or family_name.startswith("browser."):
        return PrimitiveAdapterBinding("playwright", "managed_browser", "Ritualist Playwright adapter")
    if action_name.startswith("desktop.") or family_name == "uia.element":
        return PrimitiveAdapterBinding("windows_uia", "desktop_uia", "Windows UI Automation adapter")
    if action_name.startswith("window.") or family_name == "window.topology":
        return PrimitiveAdapterBinding("window_manager", "desktop_window", "Window management adapter")
    if action_name.startswith("app.launch"):
        return PrimitiveAdapterBinding("subprocess", "process_launcher", "Structured process launch")
    if action_name.startswith("target."):
        return PrimitiveAdapterBinding(
            "target_resolution",
            "local_target_readiness",
            "Target resolution and readiness providers",
        )
    if "process" in action_name:
        return PrimitiveAdapterBinding("psutil", "process_inspection", "Local process inspection")
    if "registry" in action_name:
        return PrimitiveAdapterBinding("winreg", "registry_read", "Windows registry read adapter")
    if action_name.startswith(("assert.file", "assert.path", "wait.for_file")):
        return PrimitiveAdapterBinding("filesystem", "local_path", "Local filesystem read adapter")
    return PrimitiveAdapterBinding("runtime", "built_in", "Ritualist runtime adapter")


def _register_read_only_primitives(registry: PrimitiveRegistry) -> None:
    for spec in _read_only_primitive_specs():
        if not registry.has(spec.primitive_id):
            registry.register(spec)


def _read_only_primitive_specs() -> tuple[PrimitiveSpec, ...]:
    specs: list[PrimitiveSpec] = []
    specs.extend(
        _read_only_specs(
            "app.process",
            {
                "list": "List visible local processes without command lines.",
                "find": "Find local processes by structured name match.",
                "is_running": "Check whether a local process is running.",
                "wait_running": "Wait until a local process appears.",
                "wait_exit": "Wait until a local process exits.",
            },
            capabilities=(PrimitiveCapability.PROCESS_INSPECTION,),
            adapter=PrimitiveAdapterBinding("psutil", "process_inspection", "Local process inventory"),
            parameters={
                "find": (_optional("name"), _optional("contains")),
                "is_running": (_optional("name"), _optional("pid")),
                "wait_running": (_optional("name"), _optional("pid"), _optional("timeout_seconds")),
                "wait_exit": (_optional("name"), _optional("pid"), _optional("timeout_seconds")),
            },
        )
    )
    specs.extend(
        _read_only_specs(
            "window.topology",
            {
                "list_windows": "List top-level desktop windows and available bounds.",
                "find_window": "Find a top-level desktop window by title or process.",
                "get_bounds": "Read bounds for a matching top-level desktop window.",
                "get_foreground": "Read the current foreground window title.",
                "monitor_list": "List monitor work-area bounds.",
            },
            capabilities=(PrimitiveCapability.WINDOWS_UIA, PrimitiveCapability.WINDOW_MANAGEMENT),
            platforms=("windows",),
            adapter=PrimitiveAdapterBinding("window_manager", "desktop_window", "Read-only window inventory"),
            parameters={
                "list_windows": (_optional("title_contains"), _optional("process_name")),
                "find_window": (_optional("title_contains"), _optional("process_name")),
                "get_bounds": (_optional("title_contains"), _optional("process_name")),
            },
        )
    )
    specs.extend(
        _read_only_specs(
            "uia.element",
            {
                "list_labels": "List visible labels inside matching windows.",
                "find_text": "Find visible text inside a scoped desktop window.",
                "find_control": "Find a visible UI Automation control by label/type.",
                "candidate_dump": "Dump visible candidate labels for diagnostics.",
            },
            capabilities=(PrimitiveCapability.WINDOWS_UIA,),
            platforms=("windows",),
            adapter=PrimitiveAdapterBinding("windows_uia", "desktop_uia", "Windows UI Automation read adapter"),
            parameters={
                "list_labels": (
                    _required("window_title_contains"),
                    _optional("control_type"),
                    _optional("limit"),
                ),
                "find_text": (
                    _required("window_title_contains"),
                    _required("text"),
                    _optional("control_type"),
                    _optional("exact"),
                ),
                "find_control": (
                    _required("window_title_contains"),
                    _required("text"),
                    _optional("control_type"),
                    _optional("exact"),
                ),
                "candidate_dump": (
                    _required("window_title_contains"),
                    _optional("control_type"),
                    _optional("limit"),
                ),
            },
        )
    )
    specs.extend(
        _read_only_specs(
            "browser.assert",
            {
                "title_matches": "Check current managed browser page title.",
                "url_matches": "Check current managed browser page URL.",
            },
            capabilities=(PrimitiveCapability.PLAYWRIGHT, PrimitiveCapability.BROWSER_CONTROL),
            adapter=PrimitiveAdapterBinding("playwright", "managed_browser", "Ritualist browser read adapter"),
            parameters={
                "title_matches": (_optional("title"), _optional("title_contains")),
                "url_matches": (_optional("url"), _optional("url_contains")),
            },
        )
    )
    specs.extend(
        _read_only_specs(
            "runtime.assert",
            {
                "value_equals": "Compare two rendered literal values without evaluating code.",
            },
            capabilities=(),
            adapter=PrimitiveAdapterBinding("runtime", "literal_comparison", "Runtime value comparison"),
            parameters={
                "value_equals": (_required("left"), _required("right")),
            },
        )
    )
    specs.extend(
        _read_only_specs(
            "hardware.inventory",
            {
                "snapshot": "Collect a redacted hardware inventory snapshot.",
                "bios": "Read basic BIOS/platform fields when available.",
                "cpu": "Read CPU model/count information.",
                "gpu": "Read GPU inventory when available without shell scripts.",
                "motherboard": "Read motherboard inventory when available without shell scripts.",
                "disks": "Read disk capacity summaries.",
                "network_adapters": "Read network adapter inventory summaries.",
                "pnp_devices": "Read Plug and Play inventory when available without shell scripts.",
            },
            capabilities=(PrimitiveCapability.HARDWARE_INVENTORY,),
            platforms=("windows",),
            adapter=PrimitiveAdapterBinding("local_inventory", "hardware_read", "Read-only hardware inventory"),
        )
    )
    specs.extend(
        _read_only_specs(
            "network.connectivity",
            {
                "snapshot": "Collect a local network connectivity snapshot.",
                "dns": "Resolve DNS for a target host.",
                "tcp": "Probe TCP connectivity without sending application data.",
                "route_hint": "Infer local route choice for a target address.",
                "profile": "Read local network profile summary.",
            },
            capabilities=(PrimitiveCapability.NETWORK_CONNECTIVITY,),
            adapter=PrimitiveAdapterBinding("python_socket", "network_read", "Read-only network connectivity probes"),
            parameters={
                "dns": (_required("host"),),
                "tcp": (_required("host"), _required("port"), _optional("timeout_seconds")),
                "route_hint": (_required("host"), _optional("port")),
            },
        )
    )
    specs.extend(
        _read_only_specs(
            "diagnostics.bundle",
            {
                "collect_minimal": "Collect a minimal redacted local diagnostics bundle.",
                "collect_support": "Collect a support diagnostics bundle without secret classes.",
                "collect_gamer_crash": "Collect a gamer crash diagnostics bundle without screenshots or secrets.",
            },
            capabilities=(PrimitiveCapability.DIAGNOSTICS_COLLECT,),
            adapter=PrimitiveAdapterBinding("diagnostics", "redacted_bundle", "Ritualist diagnostics artifact writer"),
            artifact_behavior="JSON, text, checksum, redaction manifest, and zip bundle",
            parameters={
                "collect_minimal": (_optional("output_dir"),),
                "collect_support": (_optional("output_dir"),),
                "collect_gamer_crash": (_optional("output_dir"),),
            },
        )
    )
    return tuple(specs)


def _read_only_specs(
    family: str,
    verbs: dict[str, str],
    *,
    capabilities: tuple[PrimitiveCapability, ...],
    adapter: PrimitiveAdapterBinding,
    platforms: tuple[PlatformName, ...] = ("windows", "macos", "linux"),
    parameters: dict[str, tuple[PrimitiveParameter, ...]] | None = None,
    artifact_behavior: str = "none",
) -> tuple[PrimitiveSpec, ...]:
    specs: list[PrimitiveSpec] = []
    for verb, description in verbs.items():
        specs.append(
            PrimitiveSpec(
                family=PrimitiveFamily(family),
                verb=PrimitiveVerb(verb),
                display_name=_primitive_display_name(family, verb),
                description=description,
                required_capabilities=capabilities,
                supported_platforms=platforms,
                risk=PrimitiveRisk.READ_ONLY,
                confirmation_policy="never",
                allowed_in_imported_packs=True,
                adapter_binding=adapter,
                parameters=(parameters or {}).get(verb, ()),
                dry_run_behavior="describe read-only primitive without probing host state",
                artifact_behavior=artifact_behavior,
                verification_behavior="read-only result status and details",
            )
        )
    return tuple(specs)


def _required(name: str) -> PrimitiveParameter:
    return PrimitiveParameter(name=name, required=True)


def _optional(name: str) -> PrimitiveParameter:
    return PrimitiveParameter(name=name, required=False)


def _primitive_display_name(family: str, verb: str) -> str:
    words = [*family.split("."), *verb.split("_")]
    return " ".join(word.capitalize() for word in words if word)


def _parameters_from_metadata(metadata: ActionMetadata) -> tuple[PrimitiveParameter, ...]:
    parameters = [
        PrimitiveParameter(name=name, required=True) for name in metadata.required_params
    ]
    parameters.extend(
        PrimitiveParameter(name=name, required=False) for name in metadata.optional_params
    )
    return tuple(parameters)


def _artifact_behavior(action_name: str) -> str:
    if action_name == "note.add":
        return "redacted operator note metadata only"
    if action_name.startswith("diagnostics."):
        return "redacted local diagnostics artifacts only"
    return "none"


def _verification_behavior(action_name: str) -> str:
    if action_name.startswith("assert.") or action_name.startswith("browser.wait_"):
        return "read-only predicate result"
    if action_name.startswith("wait."):
        return "wait condition result"
    return "result status only"


def _display_name(action_name: str) -> str:
    category, _, verb = action_name.partition(".")
    words = [*verb.split("_"), category]
    return " ".join(word.capitalize() for word in words if word)


def _validate_family(value: str) -> None:
    if not _PRIMITIVE_NAME_PATTERN.fullmatch(value):
        raise ValueError("primitive family must be lowercase dotted snake_case")


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
