from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import RitualistError
from .models import SAFE_ID_PATTERN
from .paths import app_data_path
from .primitives import (
    PrimitivePlan,
    PrimitivePlanStep,
    PrimitiveRegistry,
    PrimitiveRisk,
    create_primitive_registry,
)


TARGET_RESOLUTION_SCHEMA_VERSION = "target.resolution.v1"
TARGET_PLAN_SCHEMA_VERSION = "target.plan.v1"
TARGET_PLAN_SUMMARY_SCHEMA_VERSION = "target.plan_summary.v1"


class TargetState(str, Enum):
    UNKNOWN = "unknown"
    NOT_FOUND = "not_found"
    RUNNING = "running"
    LAUNCHABLE = "launchable"
    LAUNCHER_MISSING = "launcher_missing"
    LAUNCHER_AVAILABLE = "launcher_available"
    LOGIN_REQUIRED = "login_required"
    INSTALL_SOURCE_AVAILABLE = "install_source_available"
    INSTALL_MEDIA_PRESENT = "install_media_present"
    INSTALL_AVAILABLE = "install_available"
    INSTALLING = "installing"
    UPDATE_AVAILABLE = "update_available"
    UPDATING = "updating"
    READY = "ready"
    LAUNCHING = "launching"
    BLOCKED = "blocked"
    FAILED = "failed"


class TargetAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    kind: str = "name"

    @field_validator("value", "kind")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("target alias fields must not be blank")
        return text


class TargetHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executable_names: tuple[str, ...] = ()
    executable_paths: tuple[str, ...] = ()
    installer_names: tuple[str, ...] = ()
    installer_paths: tuple[str, ...] = ()
    window_titles: tuple[str, ...] = ()
    shortcut_names: tuple[str, ...] = ()
    media_volume_labels: tuple[str, ...] = ()
    installed_app_names: tuple[str, ...] = ()
    launcher_hints: tuple[str, ...] = ()

    @field_validator(
        "executable_names",
        "executable_paths",
        "installer_names",
        "installer_paths",
        "window_titles",
        "shortcut_names",
        "media_volume_labels",
        "installed_app_names",
        "launcher_hints",
        mode="before",
    )
    @classmethod
    def normalize_strings(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple)):
            values = list(value)
        else:
            raise ValueError("target hints must be strings or string lists")
        return tuple(str(item).strip() for item in values if str(item).strip())


class TargetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    display_name: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("target id must be a safe filename-like identifier")
        return value

    @field_validator("kind", "display_name")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("target identity fields must not be blank")
        return text


class TargetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    display_name: str
    aliases: tuple[TargetAlias, ...] = ()
    hints: TargetHint = Field(default_factory=TargetHint)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("target id must be a safe filename-like identifier")
        return value

    @field_validator("kind", "display_name")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("target fields must not be blank")
        return text

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: object) -> tuple[dict[str, str], ...]:
        if value is None:
            return ()
        aliases = [value] if isinstance(value, str) else list(value) if isinstance(value, (tuple, list)) else value
        if not isinstance(aliases, list):
            raise ValueError("aliases must be a list")
        rows: list[dict[str, str]] = []
        for item in aliases:
            if isinstance(item, str):
                rows.append({"value": item})
            elif isinstance(item, dict):
                rows.append(dict(item))
            else:
                raise ValueError("aliases must contain strings or mappings")
        return tuple(rows)

    @property
    def identity(self) -> TargetIdentity:
        return TargetIdentity(id=self.id, kind=self.kind, display_name=self.display_name)

    def names(self) -> tuple[str, ...]:
        rows = [self.id, self.display_name]
        rows.extend(alias.value for alias in self.aliases)
        rows.extend(self.hints.shortcut_names)
        rows.extend(self.hints.installed_app_names)
        return tuple(dict.fromkeys(row for row in rows if row))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "display_name": self.display_name,
            "aliases": [alias.model_dump(mode="json") for alias in self.aliases],
            "hints": self.hints.model_dump(mode="json"),
        }


class TargetProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    description: str = ""
    states: tuple[TargetState, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "states": [state.value for state in self.states],
        }


class TargetTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    from_state: TargetState
    to_state: TargetState
    primitive_id: str | None = None
    action_name: str | None = None
    requires_confirmation: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "primitive_id": self.primitive_id,
            "action_name": self.action_name,
            "requires_confirmation": self.requires_confirmation,
            "summary": self.summary,
        }


class TargetCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    target_id: str
    provider: str
    state: TargetState = TargetState.UNKNOWN
    label: str
    confidence: float = 0.5
    path: str | None = None
    command: str | None = None
    process_name: str | None = None
    process_id: int | None = None
    window_title: str | None = None
    volume_label: str | None = None
    transition: TargetTransition | None = None
    possible_transitions: tuple[TargetTransition, ...] = ()
    evidence: tuple[str, ...] = ()
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_id", "target_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("target candidate ids must be safe filename-like identifiers")
        return value

    @field_validator("label", "provider")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("target candidate fields must not be blank")
        return text

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "target_id": self.target_id,
            "provider": self.provider,
            "state": self.state.value,
            "label": self.label,
            "confidence": self.confidence,
            "path": self.path,
            "command": self.command,
            "process_name": self.process_name,
            "process_id": self.process_id,
            "window_title": self.window_title,
            "volume_label": self.volume_label,
            "transition": self.transition.to_dict() if self.transition else None,
            "possible_transitions": [
                transition.to_dict() for transition in self.possible_transitions
            ],
            "evidence": list(self.evidence),
            "details": self.details,
        }


class TargetResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    query: str
    target: TargetSpec | None = None
    state: TargetState = TargetState.UNKNOWN
    candidates: tuple[TargetCandidate, ...] = ()
    diagnostics: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    providers: tuple[TargetProvider, ...] = ()
    matched_alias: str | None = None
    schema_version: str = TARGET_RESOLUTION_SCHEMA_VERSION

    @property
    def best_candidate(self) -> TargetCandidate | None:
        return self.candidates[0] if self.candidates else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "query": self.query,
            "target": self.target.to_dict() if self.target else None,
            "matched_alias": self.matched_alias,
            "state": self.state.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "diagnostics": list(self.diagnostics),
            "suggestions": list(self.suggestions),
            "providers": [provider.to_dict() for provider in self.providers],
        }


class TargetPlanSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    target_display_name: str
    state: TargetState
    best_candidate_summary: str = ""
    risk_summary: dict[str, int] = Field(default_factory=dict)
    confirmation_count: int = 0
    unresolved_questions: tuple[str, ...] = ()
    recommended_next_action: str = ""
    last_successful_source: str | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = TARGET_PLAN_SUMMARY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "target_display_name": self.target_display_name,
            "state": self.state.value,
            "best_candidate_summary": self.best_candidate_summary,
            "risk_summary": dict(self.risk_summary),
            "confirmation_count": self.confirmation_count,
            "unresolved_questions": list(self.unresolved_questions),
            "recommended_next_action": self.recommended_next_action,
            "last_successful_source": self.last_successful_source,
            "readiness": self.readiness,
        }


class TargetMemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    provider_id: str
    path: str | None = None
    command: str | None = None
    last_successful_state: TargetState = TargetState.LAUNCHABLE
    timestamp: str = ""
    evidence: tuple[str, ...] = ()
    scope: str = "local_machine_user"

    @field_validator("target_id")
    @classmethod
    def validate_target_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("target memory target_id must be a safe filename-like identifier")
        return value

    @field_validator("provider_id", "scope")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("target memory fields must not be blank")
        return text

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class TargetCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: tuple[TargetSpec, ...]

    def resolve(self, query: str) -> tuple[TargetSpec | None, str | None]:
        normalized = normalize_target_name(query)
        for target in self.targets:
            for name in target.names():
                if normalize_target_name(name) == normalized:
                    return target, name
        return None, None


class TargetDiscoveryProvider(Protocol):
    def provider_info(self) -> TargetProvider: ...

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery: ...

    def build_plan(
        self,
        candidate: TargetCandidate,
        policy_context: dict[str, Any] | None = None,
    ) -> TargetPlanSummary: ...


PrimitiveRunner = Callable[[str, dict[str, Any]], Any]


@dataclass(frozen=True)
class ProviderDiscovery:
    provider: TargetProvider
    candidates: tuple[TargetCandidate, ...] = ()
    diagnostics: tuple[str, ...] = ()


TargetProviderResult = ProviderDiscovery


@dataclass(frozen=True)
class TargetDiscoveryContext:
    primitive_runner: PrimitiveRunner | None = None
    start_menu_roots: tuple[Path, ...] = ()
    desktop_roots: tuple[Path, ...] = ()
    executable_roots: tuple[Path, ...] = ()
    removable_roots: tuple[Path, ...] = ()
    memory_path: Path | None = None

    @classmethod
    def default(cls) -> TargetDiscoveryContext:
        return cls(
            primitive_runner=_default_primitive_runner,
            start_menu_roots=tuple(_existing_paths(_default_start_menu_roots())),
            desktop_roots=tuple(_existing_paths(_default_desktop_roots())),
            executable_roots=(),
            removable_roots=tuple(_existing_paths(_default_removable_roots())),
            memory_path=app_data_path() / "target-memory.json",
        )


def builtin_target_catalog() -> TargetCatalog:
    return TargetCatalog(
        targets=(
            TargetSpec(
                id="diablo_iv",
                kind="game",
                display_name="Diablo IV",
                aliases=("Diablo 4", "D4"),
                hints=TargetHint(
                    executable_names=("Diablo IV.exe",),
                    window_titles=("Diablo IV",),
                    shortcut_names=("Diablo IV",),
                    media_volume_labels=("DIABLO_IV", "DIABLO4"),
                    launcher_hints=("battle_net",),
                ),
            ),
        )
    )


def default_target_providers() -> tuple[TargetDiscoveryProvider, ...]:
    from ritualist.integrations.battlenet_readiness import BattleNetReadinessProvider

    return (
        RunningProcessProvider(),
        BattleNetReadinessProvider(),
        UserMemoryProvider(),
        StartMenuShortcutProvider(),
        DesktopShortcutProvider(),
        ExecutablePathProvider(),
        InstalledAppsProvider(),
        RemovableMediaProvider(),
    )


def resolve_target(
    query: str,
    *,
    catalog: TargetCatalog | None = None,
    providers: tuple[TargetDiscoveryProvider, ...] | None = None,
    context: TargetDiscoveryContext | None = None,
) -> TargetResolutionResult:
    resolved_catalog = catalog or builtin_target_catalog()
    target, matched_alias = resolved_catalog.resolve(query)
    provider_rows = tuple(default_target_providers() if providers is None else providers)
    provider_infos = tuple(provider.provider_info() for provider in provider_rows)
    if target is None:
        return TargetResolutionResult(
            query=query,
            state=TargetState.NOT_FOUND,
            diagnostics=(f"target not found in local catalog: {query}",),
            suggestions=_not_found_suggestions(),
            providers=provider_infos,
        )

    resolved_context = context or TargetDiscoveryContext.default()
    candidates: list[TargetCandidate] = []
    diagnostics: list[str] = []
    for provider in provider_rows:
        try:
            discovery = provider.discover(target, resolved_context)
        except Exception as exc:  # noqa: BLE001 - target discovery is best effort.
            info = provider.provider_info()
            diagnostics.append(f"{info.id} provider failed: {exc}")
            continue
        candidates.extend(discovery.candidates)
        diagnostics.extend(discovery.diagnostics)

    ordered = tuple(sorted(candidates, key=_candidate_sort_key))
    state = ordered[0].state if ordered else TargetState.NOT_FOUND
    return TargetResolutionResult(
        query=query,
        target=target,
        state=state,
        candidates=ordered,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        suggestions=_suggestions_for_state(state),
        providers=provider_infos,
        matched_alias=matched_alias,
    )


def compile_target_start_plan(
    target_id_or_name: str,
    *,
    resolution: TargetResolutionResult | None = None,
    intent_metadata: dict[str, object] | None = None,
    primitive_registry: PrimitiveRegistry | None = None,
) -> PrimitivePlan:
    registry = primitive_registry or create_primitive_registry()
    resolved = resolution or resolve_target(target_id_or_name)
    target = resolved.target
    target_id = target.id if target is not None else normalize_target_name(target_id_or_name) or "unknown"
    display_name = target.display_name if target is not None else target_id_or_name
    intent = intent_metadata or {
        "schema_version": "intent.v1",
        "intent_id": f"target_start_{target_id}",
        "kind": "target.start",
        "display_name": f"Start {display_name}",
        "description": "Start a local target using deterministic target resolution.",
        "target": target_id_or_name,
        "requested_outcome": f"Resolve and prepare to start {display_name}.",
        "constraints": {},
        "preferences": {},
        "risk_budget": PrimitiveRisk.CONTROLS_UI.value,
        "user_visible_summary": f"Resolve local ways to start {display_name}.",
    }
    plan_id = str(intent.get("intent_id") or f"target_start_{target_id}")
    steps: list[PrimitivePlanStep] = []
    unresolved: list[str] = []
    cleanup = ["Target plan preview does not launch apps, click UI, install software, or write files."]
    ranked_candidates = tuple(sorted(resolved.candidates, key=_candidate_sort_key))
    ranked_resolution = (
        resolved.model_copy(update={"candidates": ranked_candidates})
        if ranked_candidates != resolved.candidates
        else resolved
    )
    ambiguous = _ambiguous_candidate_choices(ranked_candidates)
    candidate = None if ambiguous else (ranked_candidates[0] if ranked_candidates else None)

    if target is None:
        unresolved.append(f"target '{target_id_or_name}' is not in the local target catalog")
    elif candidate is None:
        if ambiguous:
            unresolved.append("Multiple possible sources found. Choose one.")
        else:
            unresolved.append(f"no local launch source was found for {display_name}")
    elif candidate.state is TargetState.RUNNING:
        title = candidate.window_title or _first(target.hints.window_titles)
        if title:
            _append_registered_plan_step(
                steps,
                "window.topology.focus",
                registry=registry,
                step_name=f"Focus existing {display_name} window",
                parameters={"title_contains": title},
            )
        else:
            _append_registered_plan_step(
                steps,
                "app.process.is_running",
                registry=registry,
                step_name=f"Confirm {display_name} process is running",
                parameters={"process_name": candidate.process_name or _first(target.hints.executable_names)},
            )
            unresolved.append(f"{display_name} appears to be running, but no window title is known to focus.")
    elif candidate.state in {TargetState.LAUNCHABLE, TargetState.READY}:
        command = _launch_command(candidate)
        if command:
            _append_registered_plan_step(
                steps,
                "app.process.launch",
                registry=registry,
                step_name=f"Launch {display_name}",
                parameters={"command": command, "wait": False},
            )
        else:
            unresolved.append(
                _candidate_recommendation(candidate)
                or f"{candidate.label} is ready but has no command path"
            )
    elif candidate.state is TargetState.LAUNCHER_AVAILABLE:
        _append_registered_plan_step(
            steps,
            "operator.prompt.prompt",
            registry=registry,
            step_name=f"Review launcher for {display_name}",
            parameters={
                "prompt": (
                    f"{display_name} appears to have installed app metadata, but no direct "
                    "executable or shortcut was found. Choose a shortcut/executable manually."
                )
            },
        )
        unresolved.append("launcher metadata is available, but no safe launch command was found")
    elif candidate.state is TargetState.INSTALL_MEDIA_PRESENT:
        recommendation = _candidate_recommendation(candidate)
        _append_registered_plan_step(
            steps,
            "operator.prompt.prompt",
            registry=registry,
            step_name=f"Confirm install media for {display_name}",
            parameters={
                "prompt": (
                    f"Install media/source for {display_name} is available. "
                    "Review it manually before taking any installer action."
                )
            },
        )
        unresolved.append(
            recommendation or "installer/media execution is not implemented by Target Resolution v1"
        )
    elif candidate.state in {TargetState.INSTALL_AVAILABLE, TargetState.UPDATE_AVAILABLE}:
        recommendation = _candidate_recommendation(candidate)
        _append_registered_plan_step(
            steps,
            "operator.prompt.prompt",
            registry=registry,
            step_name=f"Review {display_name} setup/update source",
            parameters={
                "prompt": (
                    recommendation
                    or f"Review the available setup/update source for {display_name} manually."
                )
            },
        )
        unresolved.append(
            recommendation
            or "automatic install/update transitions are not implemented by Target Resolution v1"
        )
    elif candidate.state is TargetState.LOGIN_REQUIRED:
        recommendation = _candidate_recommendation(candidate)
        _append_registered_plan_step(
            steps,
            "operator.prompt.prompt",
            registry=registry,
            step_name=f"Manual login required for {display_name}",
            parameters={
                "prompt": recommendation or f"Log in manually, then resume {display_name}."
            },
        )
        if recommendation:
            unresolved.append(recommendation)
    else:
        unresolved.append(
            _candidate_recommendation(candidate)
            or f"target state {candidate.state.value} has no executable transition in v1"
        )

    unresolved.extend(ranked_resolution.suggestions if ranked_resolution.state is TargetState.NOT_FOUND else ())
    intent = _target_intent_with_resolution(intent, ranked_resolution, selected_candidate=candidate)
    return _build_target_plan(
        plan_id,
        intent=intent,
        steps=steps,
        registry=registry,
        unresolved_questions=tuple(dict.fromkeys(unresolved)),
        rollback_or_cleanup_notes=cleanup,
        verification_steps=(
            f"Target resolution state: {ranked_resolution.state.value}",
            f"Candidates discovered: {len(ranked_resolution.candidates)}",
        ),
    )


def target_plan_payload(
    resolution: TargetResolutionResult,
    plan: PrimitivePlan,
    doctor: Any,
) -> dict[str, object]:
    return {
        "schema_version": TARGET_PLAN_SCHEMA_VERSION,
        "resolution": resolution.to_dict(),
        "plan": plan.to_dict(),
        "doctor": doctor.to_dict(),
        "home_summary": build_target_plan_summary(resolution, plan, doctor).to_dict(),
    }


def build_target_plan_summary(
    resolution: TargetResolutionResult,
    plan: PrimitivePlan,
    doctor: Any | None = None,
) -> TargetPlanSummary:
    target_name = resolution.target.display_name if resolution.target else resolution.query
    candidate = resolution.best_candidate
    doctor_status = ""
    if doctor is not None:
        compatibility = getattr(doctor, "compatibility", "")
        doctor_status = str(compatibility or "")
    return TargetPlanSummary(
        title=f"Start {target_name}",
        target_display_name=target_name,
        state=resolution.state,
        best_candidate_summary=_candidate_summary(candidate),
        risk_summary=dict(plan.risk_summary),
        confirmation_count=len(plan.confirmations_needed),
        unresolved_questions=tuple(plan.unresolved_questions),
        recommended_next_action=_recommended_next_action(resolution, plan, doctor_status=doctor_status),
        last_successful_source=(
            candidate.command or candidate.path
            if candidate is not None and candidate.provider == "user_memory"
            else None
        ),
        readiness=_candidate_readiness(candidate),
    )


class _TargetProviderPlanMixin:
    def build_plan(
        self,
        candidate: TargetCandidate,
        policy_context: dict[str, Any] | None = None,
    ) -> TargetPlanSummary:
        del policy_context
        plan = PrimitivePlan(
            plan_id=f"target_candidate_{candidate.candidate_id}",
            steps=(),
            intent={
                "schema_version": "intent.v1",
                "intent_id": f"target_candidate_{candidate.candidate_id}",
                "kind": "target.start",
                "target": candidate.target_id,
                "user_visible_summary": f"Review {candidate.label}.",
            },
            unresolved_questions=("Provider plan summaries are preview-only in Target Resolution v1.",),
        )
        resolution = TargetResolutionResult(
            query=candidate.target_id,
            state=candidate.state,
            candidates=(candidate,),
        )
        return build_target_plan_summary(resolution, plan)


class RunningProcessProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="running_process",
            display_name="Running process",
            description="Uses read-only app.process primitives to find active local processes.",
            states=(TargetState.RUNNING,),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        runner = context.primitive_runner
        if runner is None:
            return ProviderDiscovery(self.provider_info(), diagnostics=("app.process primitive runner unavailable",))
        candidates: list[TargetCandidate] = []
        diagnostics: list[str] = []
        for executable_name in target.hints.executable_names:
            try:
                result = runner("app.process.find", {"name": executable_name})
            except RitualistError as exc:
                diagnostics.append(f"could not inspect process {executable_name}: {exc}")
                continue
            for row in _result_rows(result, "processes"):
                pid = _int_or_none(row.get("pid"))
                candidates.append(
                    TargetCandidate(
                        candidate_id=_candidate_id("running", target.id, executable_name, str(pid or "")),
                        target_id=target.id,
                        provider=self.provider_info().id,
                        state=TargetState.RUNNING,
                        label=f"running process {executable_name}",
                        confidence=0.95,
                        process_name=executable_name,
                        process_id=pid,
                        window_title=_first(target.hints.window_titles),
                        evidence=(f"Found running process: {executable_name}",),
                        details={"process": row},
                    )
                )
        return ProviderDiscovery(self.provider_info(), candidates=tuple(candidates), diagnostics=tuple(diagnostics))


class StartMenuShortcutProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="start_menu_shortcut",
            display_name="Start Menu shortcut",
            description="Finds local Start Menu shortcuts by filename.",
            states=(TargetState.LAUNCHABLE,),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        return _discover_shortcuts(
            target,
            roots=context.start_menu_roots,
            provider=self.provider_info(),
            label_prefix="Start Menu shortcut",
        )


class DesktopShortcutProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="desktop_shortcut",
            display_name="Desktop shortcut",
            description="Finds local desktop shortcuts by filename.",
            states=(TargetState.LAUNCHABLE,),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        return _discover_shortcuts(
            target,
            roots=context.desktop_roots,
            provider=self.provider_info(),
            label_prefix="Desktop shortcut",
        )


class ExecutablePathProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="executable_path",
            display_name="Executable path",
            description="Finds explicit local executable or installer paths from target hints.",
            states=(TargetState.LAUNCHABLE, TargetState.INSTALL_AVAILABLE),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        candidates: list[TargetCandidate] = []
        diagnostics: list[str] = []
        for raw_path in target.hints.executable_paths:
            path = _expand_path(raw_path)
            if path.is_file():
                candidates.append(_path_candidate(target, self.provider_info(), path, TargetState.LAUNCHABLE))
            else:
                diagnostics.append(f"executable path not found: {path}")
        for executable_name in target.hints.executable_names:
            resolved = shutil.which(executable_name)
            if resolved:
                candidates.append(
                    _path_candidate(target, self.provider_info(), Path(resolved), TargetState.LAUNCHABLE)
                )
            candidates.extend(
                _search_roots_for_name(
                    target,
                    provider=self.provider_info(),
                    roots=context.executable_roots,
                    name=executable_name,
                    state=TargetState.LAUNCHABLE,
                )
            )
        for raw_path in target.hints.installer_paths:
            path = _expand_path(raw_path)
            if path.is_file():
                candidates.append(_path_candidate(target, self.provider_info(), path, TargetState.INSTALL_AVAILABLE))
            else:
                diagnostics.append(f"installer path not found: {path}")
        for installer_name in target.hints.installer_names:
            candidates.extend(
                _search_roots_for_name(
                    target,
                    provider=self.provider_info(),
                    roots=context.executable_roots,
                    name=installer_name,
                    state=TargetState.INSTALL_AVAILABLE,
                )
            )
        return ProviderDiscovery(
            self.provider_info(),
            candidates=tuple(_dedupe_candidates(candidates)),
            diagnostics=tuple(diagnostics),
        )


class InstalledAppsProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="installed_apps",
            display_name="Installed apps metadata",
            description="Best-effort read-only installed-app metadata inspection.",
            states=(TargetState.LAUNCHER_AVAILABLE, TargetState.LAUNCHABLE),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        if sys.platform != "win32":
            return ProviderDiscovery(
                self.provider_info(),
                diagnostics=("installed app metadata provider is currently Windows-only",),
            )
        try:
            rows = list(_windows_installed_app_rows())
        except Exception as exc:  # noqa: BLE001 - best effort registry provider.
            return ProviderDiscovery(self.provider_info(), diagnostics=(f"could not read installed apps: {exc}",))

        candidates: list[TargetCandidate] = []
        names = tuple(target.names())
        for row in rows:
            display_name = str(row.get("display_name") or "")
            if not _matches_any_name(display_name, names):
                continue
            install_location = str(row.get("install_location") or "")
            launch_path = _first_existing_child(install_location, target.hints.executable_names)
            state = TargetState.LAUNCHABLE if launch_path else TargetState.LAUNCHER_AVAILABLE
            candidates.append(
                TargetCandidate(
                    candidate_id=_candidate_id("installed", target.id, display_name),
                    target_id=target.id,
                    provider=self.provider_info().id,
                    state=state,
                    label=f"installed app metadata: {display_name}",
                    confidence=0.7,
                    path=str(launch_path) if launch_path else install_location or None,
                    command=str(launch_path) if launch_path else None,
                    evidence=(f"Found installed app metadata: {display_name}",),
                    details={key: value for key, value in row.items() if value},
                )
            )
        return ProviderDiscovery(self.provider_info(), candidates=tuple(candidates))


class RemovableMediaProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="removable_media",
            display_name="Removable media",
            description="Finds local CD/USB/removable media sources without modifying them.",
            states=(TargetState.INSTALL_MEDIA_PRESENT,),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        candidates: list[TargetCandidate] = []
        expected_labels = {_normalize_label(label) for label in target.hints.media_volume_labels}
        explicit_installer_names = tuple(target.hints.installer_names)
        for root in context.removable_roots:
            if not root.exists():
                continue
            label = _volume_label(root)
            label_matches = bool(expected_labels and _normalize_label(label) in expected_labels)
            installer_names = (
                explicit_installer_names
                if explicit_installer_names
                else ("setup.exe", "install.exe")
                if label_matches
                else ()
            )
            installers = [path for name in installer_names for path in root.glob(name) if path.is_file()]
            if not label_matches and not installers:
                continue
            command = str(installers[0]) if installers else None
            candidates.append(
                TargetCandidate(
                    candidate_id=_candidate_id("media", target.id, label or str(root)),
                    target_id=target.id,
                    provider=self.provider_info().id,
                    state=TargetState.INSTALL_MEDIA_PRESENT,
                    label=f"install media {label or root}",
                    confidence=0.85 if label_matches else 0.55,
                    path=str(root),
                    command=command,
                    volume_label=label,
                    evidence=tuple(
                        item
                        for item in (
                            f"Found removable volume {root} labeled {label}" if label else "",
                            f"Found installer candidate: {command}" if command else "",
                        )
                        if item
                    ),
                    details={"installer": command, "root": str(root)},
                )
            )
        return ProviderDiscovery(self.provider_info(), candidates=tuple(candidates))


class UserMemoryProvider(_TargetProviderPlanMixin):
    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id="user_memory",
            display_name="User memory",
            description="Reads prior local target resolution memory if present.",
            states=(TargetState.LAUNCHABLE, TargetState.READY),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        path = context.memory_path
        if path is None or not path.exists():
            return ProviderDiscovery(self.provider_info())
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ProviderDiscovery(self.provider_info(), diagnostics=(f"could not read target memory: {exc}",))
        rows = _memory_rows(raw, target.id)
        candidates: list[TargetCandidate] = []
        diagnostics: list[str] = []
        for index, row in enumerate(rows):
            if _contains_sensitive_key(row):
                diagnostics.append("ignored target memory entry containing sensitive keys")
                continue
            command = str(row.get("command") or row.get("path") or "").strip()
            if not command:
                continue
            remembered_state = _target_state(row.get("state")) or TargetState.LAUNCHABLE
            state = (
                remembered_state
                if remembered_state in {TargetState.LAUNCHABLE, TargetState.READY}
                else TargetState.LAUNCHABLE
            )
            if command:
                command_path = _expand_path(command)
                if not command_path.exists():
                    continue
                command = str(command_path)
            candidates.append(
                TargetCandidate(
                    candidate_id=_candidate_id("memory", target.id, str(index)),
                    target_id=target.id,
                    provider=self.provider_info().id,
                    state=state,
                    label=str(row.get("label") or "remembered local target"),
                    confidence=float(row.get("confidence") or 0.65),
                    path=command or None,
                    command=command or None,
                    window_title=str(row.get("window_title") or "") or None,
                    evidence=("Found prior local target memory entry",),
                    details={"source": "target-memory"},
                )
            )
        return ProviderDiscovery(self.provider_info(), candidates=tuple(candidates), diagnostics=tuple(diagnostics))


def normalize_target_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _default_primitive_runner(primitive_id: str, parameters: dict[str, Any]) -> Any:
    from .primitive_runtime import run_read_only_primitive

    return run_read_only_primitive(primitive_id, parameters=parameters)


def _default_start_menu_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    program_data = os.environ.get("ProgramData")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return tuple(roots)


def _default_desktop_roots() -> tuple[Path, ...]:
    roots = [Path.home() / "Desktop"]
    public = os.environ.get("PUBLIC")
    if public:
        roots.append(Path(public) / "Desktop")
    return tuple(roots)


def _default_removable_roots() -> tuple[Path, ...]:
    if sys.platform == "win32":
        return _windows_removable_roots()
    return tuple(_non_windows_removable_roots((Path("/Volumes"), Path("/media"), Path("/run/media"))))


def _existing_paths(paths: tuple[Path, ...]) -> list[Path]:
    return [path for path in paths if path.exists()]


def _discover_shortcuts(
    target: TargetSpec,
    *,
    roots: tuple[Path, ...],
    provider: TargetProvider,
    label_prefix: str,
) -> ProviderDiscovery:
    candidates: list[TargetCandidate] = []
    for root in roots:
        for path in _safe_rglob(root, ("*.lnk", "*.url")):
            if not _matches_shortcut(path, target):
                continue
            candidates.append(
                TargetCandidate(
                    candidate_id=_candidate_id(provider.id, target.id, path.stem),
                    target_id=target.id,
                    provider=provider.id,
                    state=TargetState.LAUNCHABLE,
                    label=f"{label_prefix}: {path.stem}",
                    confidence=0.8,
                    path=str(path),
                    command=str(path),
                    evidence=(f"Found {label_prefix}: {path.stem}",),
                    details={"root": str(root)},
                )
            )
    return ProviderDiscovery(provider, candidates=tuple(_dedupe_candidates(candidates)))


def _safe_rglob(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    rows: list[Path] = []
    if not root.exists():
        return rows
    for pattern in patterns:
        try:
            rows.extend(path for path in root.rglob(pattern) if path.is_file())
        except OSError:
            continue
    return rows


def _matches_shortcut(path: Path, target: TargetSpec) -> bool:
    names = tuple(target.hints.shortcut_names) or target.names()
    return _matches_any_name(path.stem, names)


def _matches_any_name(value: str, names: tuple[str, ...]) -> bool:
    normalized = normalize_target_name(value)
    return any(normalized == normalize_target_name(name) for name in names)


def _path_candidate(
    target: TargetSpec,
    provider: TargetProvider,
    path: Path,
    state: TargetState,
) -> TargetCandidate:
    return TargetCandidate(
        candidate_id=_candidate_id(provider.id, target.id, path.stem),
        target_id=target.id,
        provider=provider.id,
        state=state,
        label=f"{state.value.replace('_', ' ')}: {path.name}",
        confidence=0.75,
        path=str(path),
        command=str(path),
        evidence=(f"Found local path: {path}",),
    )


def _search_roots_for_name(
    target: TargetSpec,
    *,
    provider: TargetProvider,
    roots: tuple[Path, ...],
    name: str,
    state: TargetState,
) -> list[TargetCandidate]:
    candidates: list[TargetCandidate] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            matches = [path for path in root.rglob(name) if path.is_file()]
        except OSError:
            continue
        for path in matches[:25]:
            candidates.append(_path_candidate(target, provider, path, state))
    return candidates


def _expand_path(value: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value))

    def replace_percent_var(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, match.group(0))

    return Path(re.sub(r"%([^%]+)%", replace_percent_var, expanded))


def _windows_installed_app_rows() -> list[dict[str, str]]:
    import winreg

    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    rows: list[dict[str, str]] = []
    for hive, key_path in roots:
        try:
            with winreg.OpenKey(hive, key_path) as root_key:
                count = winreg.QueryInfoKey(root_key)[0]
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(root_key, index)
                        with winreg.OpenKey(root_key, subkey_name) as subkey:
                            display_name = _registry_string(winreg, subkey, "DisplayName")
                            if not display_name:
                                continue
                            rows.append(
                                {
                                    "display_name": display_name,
                                    "install_location": _registry_string(winreg, subkey, "InstallLocation"),
                                    "display_icon": _registry_string(winreg, subkey, "DisplayIcon"),
                                    "publisher": _registry_string(winreg, subkey, "Publisher"),
                                }
                            )
                    except OSError:
                        continue
        except OSError:
            continue
    return rows


def _registry_string(winreg: Any, key: Any, name: str) -> str:
    try:
        value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value).strip()


def _first_existing_child(root: str, names: tuple[str, ...]) -> Path | None:
    if not root:
        return None
    root_path = Path(root)
    for name in names:
        candidate = root_path / name
        if candidate.is_file():
            return candidate
    return None


def _volume_label(root: Path) -> str:
    label_file = root / ".volume_label"
    if label_file.is_file():
        try:
            label = label_file.read_text(encoding="utf-8").strip()
            if label:
                return label
        except OSError:
            pass
    if sys.platform == "win32":
        label = _windows_volume_label(root)
        if label:
            return label
    return root.name.rstrip("\\/") or str(root).rstrip("\\/")


def _windows_removable_roots() -> tuple[Path, ...]:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        bitmask = int(kernel32.GetLogicalDrives())
        rows: list[Path] = []
        for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            if not bitmask & (1 << index):
                continue
            root = f"{letter}:\\"
            drive_type = int(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
            if drive_type in {2, 5}:  # DRIVE_REMOVABLE, DRIVE_CDROM
                rows.append(Path(root))
        return tuple(rows)
    except Exception:  # noqa: BLE001 - fallback keeps discovery best effort.
        return tuple(Path(f"{letter}:\\") for letter in "DEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists())


def _windows_volume_label(root: Path) -> str:
    try:
        import ctypes

        label_buffer = ctypes.create_unicode_buffer(261)
        filesystem_buffer = ctypes.create_unicode_buffer(261)
        serial_number = ctypes.c_uint32()
        max_component_length = ctypes.c_uint32()
        filesystem_flags = ctypes.c_uint32()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(str(root)),
            label_buffer,
            len(label_buffer),
            ctypes.byref(serial_number),
            ctypes.byref(max_component_length),
            ctypes.byref(filesystem_flags),
            filesystem_buffer,
            len(filesystem_buffer),
        )
        return label_buffer.value.strip() if ok else ""
    except Exception:  # noqa: BLE001 - fallback to path-derived label.
        return ""


def _non_windows_removable_roots(base_roots: tuple[Path, ...]) -> list[Path]:
    rows: list[Path] = []
    for base in base_roots:
        if not base.exists():
            continue
        rows.append(base)
        try:
            rows.extend(child for child in base.iterdir() if child.is_dir())
        except OSError:
            continue
    return rows


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _memory_rows(raw: object, target_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    targets = raw.get("targets")
    if not isinstance(targets, dict):
        return []
    rows = targets.get(target_id)
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold()
            if any(marker in normalized for marker in ("password", "passwd", "secret", "token", "api_key")):
                return True
            if _contains_sensitive_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _target_state(value: object) -> TargetState | None:
    if value is None:
        return None
    try:
        return TargetState(str(value))
    except ValueError:
        return None


def _result_rows(result: Any, key: str) -> list[dict[str, Any]]:
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return []
    rows = details.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _candidate_sort_key(candidate: TargetCandidate) -> tuple[int, int, float, str]:
    return (
        -_STATE_PRIORITY.get(candidate.state, 0),
        -_PROVIDER_PRIORITY.get(candidate.provider, 0),
        -candidate.confidence,
        candidate.label.casefold(),
    )


_STATE_PRIORITY: dict[TargetState, int] = {
    TargetState.RUNNING: 100,
    TargetState.READY: 95,
    TargetState.LAUNCHING: 94,
    TargetState.UPDATING: 93,
    TargetState.UPDATE_AVAILABLE: 92,
    TargetState.INSTALL_AVAILABLE: 91,
    TargetState.INSTALL_SOURCE_AVAILABLE: 91,
    TargetState.LOGIN_REQUIRED: 91,
    TargetState.BLOCKED: 91,
    TargetState.LAUNCHABLE: 90,
    TargetState.LAUNCHER_AVAILABLE: 75,
    TargetState.LAUNCHER_MISSING: 70,
    TargetState.INSTALL_MEDIA_PRESENT: 65,
    TargetState.INSTALLING: 60,
    TargetState.FAILED: 0,
    TargetState.NOT_FOUND: 0,
    TargetState.UNKNOWN: 0,
}

_PROVIDER_PRIORITY: dict[str, int] = {
    "running_process": 100,
    "battle_net_readiness": 95,
    "user_memory": 90,
    "start_menu_shortcut": 80,
    "desktop_shortcut": 75,
    "executable_path": 70,
    "installed_apps": 60,
    "removable_media": 40,
}


def _ambiguous_candidate_choices(candidates: tuple[TargetCandidate, ...]) -> tuple[TargetCandidate, ...]:
    if len(candidates) < 2:
        return ()
    first = candidates[0]
    ambiguous = [first]
    first_state_priority = _STATE_PRIORITY.get(first.state, 0)
    first_provider_priority = _PROVIDER_PRIORITY.get(first.provider, 0)
    for candidate in candidates[1:]:
        if _STATE_PRIORITY.get(candidate.state, 0) != first_state_priority:
            break
        if _PROVIDER_PRIORITY.get(candidate.provider, 0) != first_provider_priority:
            break
        if abs(candidate.confidence - first.confidence) > 0.05:
            break
        ambiguous.append(candidate)
    unique_sources = {
        candidate.command or candidate.path or candidate.window_title or candidate.label
        for candidate in ambiguous
    }
    return tuple(ambiguous) if len(unique_sources) > 1 else ()


def _target_intent_with_resolution(
    intent: dict[str, object],
    resolution: TargetResolutionResult,
    *,
    selected_candidate: TargetCandidate | None,
) -> dict[str, object]:
    updated = dict(intent)
    updated["target_resolution"] = {
        "schema_version": resolution.schema_version,
        "state": resolution.state.value,
        "selected_candidate_id": selected_candidate.candidate_id if selected_candidate else None,
        "candidate_ranking": [
            {
                "candidate_id": candidate.candidate_id,
                "provider": candidate.provider,
                "state": candidate.state.value,
                "confidence": candidate.confidence,
                "label": candidate.label,
            }
            for candidate in resolution.candidates
        ],
        "diagnostics": list(resolution.diagnostics),
        "suggestions": list(resolution.suggestions),
    }
    return updated


def _candidate_summary(candidate: TargetCandidate | None) -> str:
    if candidate is None:
        return ""
    source = candidate.command or candidate.path or candidate.window_title or candidate.label
    return f"{candidate.provider}: {candidate.state.value} - {source}"


def _candidate_readiness(candidate: TargetCandidate | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    readiness = candidate.details.get("readiness")
    return dict(readiness) if isinstance(readiness, dict) else {}


def _candidate_recommendation(candidate: TargetCandidate | None) -> str:
    if candidate is None:
        return ""
    value = candidate.details.get("recommendation")
    return str(value or "").strip()


def _recommended_next_action(
    resolution: TargetResolutionResult,
    plan: PrimitivePlan,
    *,
    doctor_status: str,
) -> str:
    if plan.unresolved_questions:
        if plan.unresolved_questions[0] == "Multiple possible sources found. Choose one.":
            return "Choose which discovered local source to use."
        return plan.unresolved_questions[0]
    if doctor_status == "incompatible":
        return "Review Doctor errors before running this target plan."
    if plan.confirmations_needed:
        return "Review the confirmation prompt before continuing."
    if resolution.state is TargetState.RUNNING:
        return "Focus the existing target window."
    if resolution.state in {TargetState.LAUNCHABLE, TargetState.READY}:
        return "Run the launch plan when ready."
    if resolution.state is TargetState.INSTALL_MEDIA_PRESENT:
        return "Review detected install media manually; Ritualist will not install silently."
    recommendation = _candidate_recommendation(resolution.best_candidate)
    if recommendation:
        return recommendation
    if resolution.state is TargetState.NOT_FOUND:
        return "Choose a local executable or shortcut for this target."
    return "Review the target plan before running."


def _suggestions_for_state(state: TargetState) -> tuple[str, ...]:
    if state is TargetState.NOT_FOUND:
        return _not_found_suggestions()
    if state is TargetState.INSTALL_MEDIA_PRESENT:
        return ("Review the detected CD/USB/removable media manually before installing.",)
    if state in {TargetState.INSTALL_AVAILABLE, TargetState.UPDATE_AVAILABLE}:
        return ("Review the detected setup/update source manually before proceeding.",)
    if state is TargetState.LOGIN_REQUIRED:
        return ("Log in manually, then rerun discovery or resume the ritual.",)
    if state in {TargetState.BLOCKED, TargetState.LAUNCHER_MISSING}:
        return ("Review the target readiness evidence before taking a desktop action.",)
    return ()


def _not_found_suggestions() -> tuple[str, ...]:
    return (
        "Choose a local executable or shortcut for this target.",
        "Insert the CD/USB/removable media if this target is installed from media.",
        "Run inspect-window to inspect visible app/window titles.",
        "Save a reviewed local target binding after you find the correct manual start path.",
    )


def _append_registered_plan_step(
    steps: list[PrimitivePlanStep],
    primitive_id: str,
    *,
    registry: PrimitiveRegistry,
    step_name: str,
    parameters: dict[str, Any],
) -> None:
    spec = registry.spec(primitive_id)
    steps.append(
        PrimitivePlanStep(
            primitive_id=primitive_id,
            action_name=spec.action_name,
            step_name=step_name,
            parameters=parameters,
            risk=spec.risk,
        )
    )


def _launch_command(candidate: TargetCandidate) -> str:
    if candidate.command:
        return candidate.command
    if not candidate.path:
        return ""
    path = Path(candidate.path)
    suffix = path.suffix.casefold()
    if suffix in {".lnk", ".url", ".exe", ".app"} or path.is_file():
        return candidate.path
    return ""


def _build_target_plan(
    plan_id: str,
    *,
    intent: dict[str, object],
    steps: list[PrimitivePlanStep],
    registry: PrimitiveRegistry,
    unresolved_questions: tuple[str, ...],
    rollback_or_cleanup_notes: list[str],
    verification_steps: tuple[str, ...],
) -> PrimitivePlan:
    required_primitives = tuple(dict.fromkeys(step.primitive_id for step in steps))
    capabilities: list[str] = []
    risk_counts: dict[str, int] = {}
    confirmations: list[str] = []
    for step in steps:
        spec = registry.spec(step.primitive_id)
        risk_counts[spec.risk.value] = risk_counts.get(spec.risk.value, 0) + 1
        for capability in spec.required_capabilities:
            if capability.value not in capabilities:
                capabilities.append(capability.value)
        if spec.confirmation_policy != "never":
            confirmations.append(f"{step.step_name or step.primitive_id}: {spec.confirmation_policy}")
    return PrimitivePlan(
        plan_id=plan_id,
        steps=tuple(steps),
        intent=intent,
        required_primitives=required_primitives,
        required_capabilities=tuple(capabilities),
        risk_summary=dict(sorted(risk_counts.items())),
        confirmations_needed=tuple(confirmations),
        artifacts_expected=(),
        verification_steps=verification_steps,
        rollback_or_cleanup_notes=tuple(rollback_or_cleanup_notes),
        unresolved_questions=unresolved_questions,
    )


def _dedupe_candidates(candidates: list[TargetCandidate]) -> list[TargetCandidate]:
    seen: set[tuple[str, str, str]] = set()
    rows: list[TargetCandidate] = []
    for candidate in candidates:
        key = (candidate.provider, candidate.state.value, candidate.command or candidate.path or candidate.label)
        if key in seen:
            continue
        seen.add(key)
        rows.append(candidate)
    return rows


def _candidate_id(*parts: str) -> str:
    text = "_".join(normalize_target_name(part) for part in parts if part)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64] or "target_candidate"


def _first(values: tuple[str, ...]) -> str | None:
    return values[0] if values else None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
