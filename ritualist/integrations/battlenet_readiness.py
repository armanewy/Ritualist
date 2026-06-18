from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
import re
import sys
from typing import Protocol

from ritualist.target_resolution import (
    ProviderDiscovery,
    TargetCandidate,
    TargetDiscoveryContext,
    TargetProvider,
    TargetSpec,
    TargetState,
    _candidate_id,
    normalize_target_name,
)

BATTLE_NET_WINDOW_TITLE = "Battle.net"
BATTLE_NET_PROVIDER_ID = "battle_net_readiness"


class BattleNetReadinessState(StrEnum):
    LAUNCHER_NOT_RUNNING = "launcher_not_running"
    LOGIN_REQUIRED = "login_required"
    GAME_NOT_SELECTED = "game_not_selected"
    INSTALL_AVAILABLE = "install_available"
    LOCATE_GAME_AVAILABLE = "locate_game_available"
    UPDATE_AVAILABLE = "update_available"
    UPDATING = "updating"
    PLAY_AVAILABLE_ENABLED = "play_available_enabled"
    PLAY_VISIBLE_BUT_DISABLED = "play_visible_but_disabled"
    LAUNCHING = "launching"
    GAME_RUNNING = "game_running"
    BLOCKED_UNKNOWN = "blocked_unknown"


@dataclass(frozen=True)
class ReadOnlyControlSnapshot:
    name: str
    control_type: str = ""
    enabled: bool = True
    visible: bool = True


@dataclass(frozen=True)
class ReadOnlyWindowSnapshot:
    title: str
    controls: tuple[ReadOnlyControlSnapshot, ...] = ()


class BattleNetWindowInspector(Protocol):
    def inspect_windows(
        self,
        *,
        title_contains: str,
        limit: int = 200,
    ) -> Sequence[ReadOnlyWindowSnapshot]:
        ...


@dataclass(frozen=True)
class BattleNetReadiness:
    state: BattleNetReadinessState
    target_state: TargetState
    label: str
    recommendation: str
    confidence: float
    evidence: tuple[str, ...]
    window_title: str | None = None
    candidate_labels: tuple[str, ...] = ()

    def details(self) -> dict[str, object]:
        return {
            "schema_version": "battle_net.readiness.v1",
            "provider": BATTLE_NET_PROVIDER_ID,
            "state": self.state.value,
            "recommendation": self.recommendation,
            "candidate_labels": list(self.candidate_labels),
            "window_title": self.window_title,
        }


class BattleNetReadinessProvider:
    def __init__(self, inspector: BattleNetWindowInspector | None = None) -> None:
        self._inspector = inspector

    def provider_info(self) -> TargetProvider:
        return TargetProvider(
            id=BATTLE_NET_PROVIDER_ID,
            display_name="Battle.net readiness",
            description=(
                "Read-only UI Automation inspection of the scoped Battle.net launcher window."
            ),
            states=(
                TargetState.LAUNCHER_MISSING,
                TargetState.LOGIN_REQUIRED,
                TargetState.INSTALL_AVAILABLE,
                TargetState.INSTALL_SOURCE_AVAILABLE,
                TargetState.UPDATE_AVAILABLE,
                TargetState.UPDATING,
                TargetState.READY,
                TargetState.BLOCKED,
                TargetState.LAUNCHING,
                TargetState.RUNNING,
            ),
        )

    def discover(
        self,
        target: TargetSpec,
        context: TargetDiscoveryContext,
    ) -> ProviderDiscovery:
        del context
        if "battle_net" not in target.hints.launcher_hints:
            return ProviderDiscovery(self.provider_info())
        inspector = self._inspector
        if inspector is None:
            if sys.platform != "win32":
                return ProviderDiscovery(
                    self.provider_info(),
                    diagnostics=("Battle.net readiness inspection is currently Windows-only",),
                )
            inspector = _WindowsBattleNetInspector()

        windows = tuple(
            inspector.inspect_windows(title_contains=BATTLE_NET_WINDOW_TITLE, limit=200)
        )
        readiness = inspect_battle_net_readiness(windows, target)
        return ProviderDiscovery(
            self.provider_info(),
            candidates=(_candidate_from_readiness(target, readiness),),
        )


class _WindowsBattleNetInspector:
    def inspect_windows(
        self,
        *,
        title_contains: str,
        limit: int = 200,
    ) -> Sequence[ReadOnlyWindowSnapshot]:
        from ritualist.adapters.windows_uia import WindowsUIAutomationAdapter

        snapshots: list[ReadOnlyWindowSnapshot] = []
        for window in WindowsUIAutomationAdapter().inspect_control_tree(
            title_contains=title_contains,
            limit=limit,
        ):
            controls = tuple(
                ReadOnlyControlSnapshot(
                    name=control.name,
                    control_type=control.control_type,
                    enabled=control.enabled,
                    visible=control.visible,
                )
                for control in window.controls
            )
            snapshots.append(ReadOnlyWindowSnapshot(title=window.title, controls=controls))
        return tuple(snapshots)


def inspect_battle_net_readiness(
    windows: Sequence[ReadOnlyWindowSnapshot],
    target: TargetSpec,
) -> BattleNetReadiness:
    scoped_windows = tuple(
        window for window in windows if _contains(window.title, BATTLE_NET_WINDOW_TITLE)
    )
    if not scoped_windows:
        return BattleNetReadiness(
            state=BattleNetReadinessState.LAUNCHER_NOT_RUNNING,
            target_state=TargetState.LAUNCHER_MISSING,
            label="Battle.net launcher is not running",
            recommendation="Open Battle.net manually, then preview Diablo IV readiness again.",
            confidence=0.7,
            evidence=("No scoped Battle.net window was visible to UI Automation.",),
        )

    window = scoped_windows[0]
    controls = tuple(control for control in window.controls if control.visible)
    candidate_labels = _candidate_labels(controls)
    evidence = [f"Inspected scoped Battle.net window: {window.title or BATTLE_NET_WINDOW_TITLE}"]
    evidence.extend(f"UIA label: {label}" for label in candidate_labels[:12])

    if _has_login_prompt(controls):
        return _readiness(
            BattleNetReadinessState.LOGIN_REQUIRED,
            TargetState.LOGIN_REQUIRED,
            "Battle.net login is required",
            "Log in to Battle.net manually, then preview Diablo IV readiness again.",
            0.9,
            evidence,
            window.title,
            candidate_labels,
        )

    if not _has_target_label(controls, target):
        return _readiness(
            BattleNetReadinessState.GAME_NOT_SELECTED,
            TargetState.BLOCKED,
            "Diablo IV is not the selected Battle.net game",
            (
                "Select Diablo IV in Battle.net manually before using Play, Install, "
                "Locate, or Update."
            ),
            0.82,
            evidence,
            window.title,
            candidate_labels,
        )

    if _has_text(controls, ("Game is running", "Now Playing", "Playing Now")):
        return _readiness(
            BattleNetReadinessState.GAME_RUNNING,
            TargetState.RUNNING,
            "Battle.net reports Diablo IV is running",
            (
                "Diablo IV appears to be running; confirm with the local process/window "
                "before focusing it."
            ),
            0.86,
            evidence,
            window.title,
            candidate_labels,
        )
    if _has_text(controls, ("Launching", "Starting game", "Playing soon")):
        return _readiness(
            BattleNetReadinessState.LAUNCHING,
            TargetState.LAUNCHING,
            "Battle.net is launching Diablo IV",
            "Wait for Diablo IV to finish launching before taking another action.",
            0.86,
            evidence,
            window.title,
            candidate_labels,
        )
    if _has_text(controls, ("Updating", "Downloading", "Initializing", "Applying update")):
        return _readiness(
            BattleNetReadinessState.UPDATING,
            TargetState.UPDATING,
            "Battle.net is updating Diablo IV",
            "Wait for the Diablo IV update to finish, then preview readiness again.",
            0.88,
            evidence,
            window.title,
            candidate_labels,
        )

    install = _button(controls, ("Install",))
    if install is not None and install.enabled:
        return _readiness(
            BattleNetReadinessState.INSTALL_AVAILABLE,
            TargetState.INSTALL_AVAILABLE,
            "Battle.net Install is available for Diablo IV",
            "Install is available. Review Battle.net manually before installing Diablo IV.",
            0.88,
            evidence,
            window.title,
            candidate_labels,
        )
    locate = _button(controls, ("Locate the game", "Locate Game", "Locate"))
    if locate is not None and locate.enabled:
        return _readiness(
            BattleNetReadinessState.LOCATE_GAME_AVAILABLE,
            TargetState.INSTALL_SOURCE_AVAILABLE,
            "Battle.net Locate the game is available for Diablo IV",
            "Locate the game is available. Use it manually only if Diablo IV is already installed.",
            0.86,
            evidence,
            window.title,
            candidate_labels,
        )
    update = _button(controls, ("Update", "Update Now"))
    if update is not None and update.enabled:
        return _readiness(
            BattleNetReadinessState.UPDATE_AVAILABLE,
            TargetState.UPDATE_AVAILABLE,
            "Battle.net Update is available for Diablo IV",
            "Update is available. Review Battle.net manually before updating Diablo IV.",
            0.88,
            evidence,
            window.title,
            candidate_labels,
        )
    play = _button(controls, ("Play",))
    if play is not None and play.enabled:
        return _readiness(
            BattleNetReadinessState.PLAY_AVAILABLE_ENABLED,
            TargetState.READY,
            "Battle.net Play is enabled for Diablo IV",
            "Play is available. Require explicit user confirmation before clicking Play.",
            0.9,
            evidence,
            window.title,
            candidate_labels,
        )
    if play is not None:
        return _readiness(
            BattleNetReadinessState.PLAY_VISIBLE_BUT_DISABLED,
            TargetState.BLOCKED,
            "Battle.net Play is visible but disabled for Diablo IV",
            "Play is visible but disabled. Wait or resolve Battle.net status manually.",
            0.84,
            evidence,
            window.title,
            candidate_labels,
        )

    return _readiness(
        BattleNetReadinessState.BLOCKED_UNKNOWN,
        TargetState.BLOCKED,
        "Battle.net readiness is ambiguous for Diablo IV",
        "Battle.net state is ambiguous. Review the launcher manually before any click.",
        0.55,
        evidence,
        window.title,
        candidate_labels,
    )


def _candidate_from_readiness(target: TargetSpec, readiness: BattleNetReadiness) -> TargetCandidate:
    return TargetCandidate(
        candidate_id=_candidate_id(BATTLE_NET_PROVIDER_ID, target.id, readiness.state.value),
        target_id=target.id,
        provider=BATTLE_NET_PROVIDER_ID,
        state=readiness.target_state,
        label=readiness.label,
        confidence=readiness.confidence,
        window_title=readiness.window_title,
        evidence=readiness.evidence,
        details={"readiness": readiness.details(), "recommendation": readiness.recommendation},
    )


def _readiness(
    state: BattleNetReadinessState,
    target_state: TargetState,
    label: str,
    recommendation: str,
    confidence: float,
    evidence: list[str],
    window_title: str,
    candidate_labels: tuple[str, ...],
) -> BattleNetReadiness:
    return BattleNetReadiness(
        state=state,
        target_state=target_state,
        label=label,
        recommendation=recommendation,
        confidence=confidence,
        evidence=tuple(dict.fromkeys(evidence)),
        window_title=window_title,
        candidate_labels=candidate_labels,
    )


def _candidate_labels(controls: Sequence[ReadOnlyControlSnapshot]) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()
    for control in controls:
        label = control.name.strip()
        if not label or label in seen:
            continue
        labels.append(label)
        seen.add(label)
        if len(labels) >= 30:
            break
    return tuple(labels)


def _button(
    controls: Sequence[ReadOnlyControlSnapshot],
    names: Sequence[str],
) -> ReadOnlyControlSnapshot | None:
    normalized = {normalize_target_name(name) for name in names}
    for control in controls:
        if not _is_button(control):
            continue
        if normalize_target_name(control.name) in normalized:
            return control
    return None


def _has_login_prompt(controls: Sequence[ReadOnlyControlSnapshot]) -> bool:
    labels = " ".join(control.name for control in controls)
    return bool(
        _has_text(controls, ("Log In", "Log in", "Email or Phone", "Password"))
        and not re.search(r"\bDiablo\s*(IV|4)\b", labels, flags=re.IGNORECASE)
    )


def _has_target_label(controls: Sequence[ReadOnlyControlSnapshot], target: TargetSpec) -> bool:
    names = (target.display_name, *[alias.value for alias in target.aliases])
    return any(_contains(control.name, name) for control in controls for name in names)


def _has_text(controls: Sequence[ReadOnlyControlSnapshot], values: Sequence[str]) -> bool:
    return any(_contains(control.name, value) for control in controls for value in values)


def _contains(value: str, needle: str) -> bool:
    return needle.casefold() in value.casefold()


def _is_button(control: ReadOnlyControlSnapshot) -> bool:
    return control.control_type.casefold() == "button" or not control.control_type
