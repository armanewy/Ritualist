from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from ritualist.cli import app
from ritualist.intent_planner import IntentSpec, compile_intent_to_plan, compile_plan_reference
from ritualist.target_resolution import (
    DesktopShortcutProvider,
    ExecutablePathProvider,
    RemovableMediaProvider,
    RunningProcessProvider,
    StartMenuShortcutProvider,
    TargetCandidate,
    TargetCatalog,
    TargetDiscoveryContext,
    TargetResolutionResult,
    TargetSpec,
    TargetState,
    UserMemoryProvider,
    builtin_target_catalog,
    compile_target_start_plan,
    resolve_target,
    target_plan_payload,
)


def _result(**details):
    return SimpleNamespace(status="success", details=details)


def test_target_spec_parsing_accepts_catalog_shape() -> None:
    spec = TargetSpec.model_validate(
        {
            "id": "vendor_app",
            "kind": "tool",
            "display_name": "Vendor App",
            "aliases": ["Vendor", {"value": "VA", "kind": "short"}],
            "hints": {"executable_names": ["Vendor.exe"], "window_titles": ["Vendor"]},
        }
    )

    assert spec.identity.id == "vendor_app"
    assert [alias.value for alias in spec.aliases] == ["Vendor", "VA"]
    assert spec.hints.executable_names == ("Vendor.exe",)


def test_alias_matching_finds_builtin_target() -> None:
    target, matched = builtin_target_catalog().resolve("Diablo 4")

    assert target is not None
    assert target.id == "diablo_iv"
    assert matched == "Diablo 4"


def test_running_process_discovery_uses_read_only_primitive() -> None:
    calls = []

    def runner(primitive_id: str, parameters: dict[str, object]):
        calls.append((primitive_id, parameters))
        return _result(processes=[{"pid": 42, "name": "Diablo IV.exe", "status": "running"}])

    result = resolve_target(
        "diablo_iv",
        providers=(RunningProcessProvider(),),
        context=TargetDiscoveryContext(primitive_runner=runner),
    )

    assert result.state is TargetState.RUNNING
    assert result.candidates[0].process_name == "Diablo IV.exe"
    assert calls == [("app.process.find", {"name": "Diablo IV.exe"})]


def test_start_menu_shortcut_discovery(tmp_path: Path) -> None:
    shortcut = tmp_path / "Games" / "Diablo IV.lnk"
    shortcut.parent.mkdir()
    shortcut.write_text("shortcut", encoding="utf-8")

    result = resolve_target(
        "D4",
        providers=(StartMenuShortcutProvider(),),
        context=TargetDiscoveryContext(start_menu_roots=(tmp_path,)),
    )

    assert result.state is TargetState.LAUNCHABLE
    assert result.candidates[0].provider == "start_menu_shortcut"
    assert result.candidates[0].command == str(shortcut)


def test_desktop_shortcut_discovery(tmp_path: Path) -> None:
    shortcut = tmp_path / "Diablo IV.url"
    shortcut.write_text("[InternetShortcut]", encoding="utf-8")

    result = resolve_target(
        "diablo_iv",
        providers=(DesktopShortcutProvider(),),
        context=TargetDiscoveryContext(desktop_roots=(tmp_path,)),
    )

    assert result.state is TargetState.LAUNCHABLE
    assert result.candidates[0].provider == "desktop_shortcut"
    assert result.candidates[0].path == str(shortcut)


def test_executable_discovery_from_search_root(tmp_path: Path) -> None:
    executable = tmp_path / "Diablo IV.exe"
    executable.write_text("exe", encoding="utf-8")

    result = resolve_target(
        "diablo_iv",
        providers=(ExecutablePathProvider(),),
        context=TargetDiscoveryContext(executable_roots=(tmp_path,)),
    )

    assert result.state is TargetState.LAUNCHABLE
    assert result.candidates[0].command == str(executable)


def test_removable_media_discovery(tmp_path: Path) -> None:
    media = tmp_path / "drive"
    media.mkdir()
    (media / ".volume_label").write_text("DIABLO4", encoding="utf-8")
    setup = media / "setup.exe"
    setup.write_text("installer", encoding="utf-8")

    result = resolve_target(
        "diablo_iv",
        providers=(RemovableMediaProvider(),),
        context=TargetDiscoveryContext(removable_roots=(media,)),
    )

    assert result.state is TargetState.INSTALL_MEDIA_PRESENT
    assert result.candidates[0].volume_label == "DIABLO4"
    assert result.candidates[0].command == str(setup)


def test_unlabeled_generic_installer_is_not_target_media(tmp_path: Path) -> None:
    media = tmp_path / "drive"
    media.mkdir()
    (media / "install.exe").write_text("installer", encoding="utf-8")

    result = resolve_target(
        "diablo_iv",
        providers=(RemovableMediaProvider(),),
        context=TargetDiscoveryContext(removable_roots=(media,)),
    )

    assert result.state is TargetState.NOT_FOUND
    assert result.candidates == ()


def test_plan_for_running_target_focuses_existing_window() -> None:
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.RUNNING,
        candidates=(
            TargetCandidate(
                candidate_id="running_diablo",
                target_id="diablo_iv",
                provider="running_process",
                state=TargetState.RUNNING,
                label="running process Diablo IV.exe",
                process_name="Diablo IV.exe",
                window_title="Diablo IV",
            ),
        ),
    )

    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    assert [step.primitive_id for step in plan.steps] == ["window.topology.focus"]
    assert plan.steps[0].parameters == {"title_contains": "Diablo IV"}


def test_plan_for_launchable_target_launches_path(tmp_path: Path) -> None:
    executable = tmp_path / "Diablo IV.exe"
    executable.write_text("exe", encoding="utf-8")
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.LAUNCHABLE,
        candidates=(
            TargetCandidate(
                candidate_id="exe_diablo",
                target_id="diablo_iv",
                provider="executable_path",
                state=TargetState.LAUNCHABLE,
                label="Diablo IV.exe",
                path=str(executable),
                command=str(executable),
            ),
        ),
    )

    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    assert [step.primitive_id for step in plan.steps] == ["app.process.launch"]
    assert plan.steps[0].parameters["command"] == str(executable)


def test_plan_for_install_media_uses_human_handoff(tmp_path: Path) -> None:
    setup = tmp_path / "setup.exe"
    setup.write_text("installer", encoding="utf-8")
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.INSTALL_MEDIA_PRESENT,
        candidates=(
            TargetCandidate(
                candidate_id="media_diablo",
                target_id="diablo_iv",
                provider="removable_media",
                state=TargetState.INSTALL_MEDIA_PRESENT,
                label="install media",
                path=str(tmp_path),
                command=str(setup),
            ),
        ),
    )

    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    assert [step.primitive_id for step in plan.steps] == ["operator.prompt.prompt"]
    assert "installer/media execution is not implemented" in plan.unresolved_questions[0]


def test_not_found_resolution_has_safe_diagnostics() -> None:
    result = resolve_target(
        "missing_app",
        catalog=TargetCatalog(targets=()),
        providers=(),
        context=TargetDiscoveryContext(),
    )

    assert result.state is TargetState.NOT_FOUND
    assert "target not found" in result.diagnostics[0]
    assert any("Choose a local executable" in suggestion for suggestion in result.suggestions)


def test_target_discovery_does_not_create_runtime_adapters(monkeypatch) -> None:
    def fail_adapter_creation():
        raise AssertionError("target discovery must not create runtime adapters")

    def fail_executor(*_args, **_kwargs):
        raise AssertionError("target discovery must not create workflow executor")

    monkeypatch.setattr("ritualist.cli.create_default_adapters", fail_adapter_creation)
    monkeypatch.setattr("ritualist.cli.WorkflowExecutor", fail_executor)

    result = resolve_target(
        "diablo_iv",
        providers=(),
        context=TargetDiscoveryContext(),
    )

    assert result.state is TargetState.NOT_FOUND


def test_explicit_empty_provider_list_does_not_use_defaults(monkeypatch) -> None:
    def fail_defaults():
        raise AssertionError("explicit providers=() must not use default providers")

    monkeypatch.setattr("ritualist.target_resolution.default_target_providers", fail_defaults)

    result = resolve_target(
        "diablo_iv",
        providers=(),
        context=TargetDiscoveryContext(),
    )

    assert result.state is TargetState.NOT_FOUND
    assert result.providers == ()


def test_launcher_available_without_command_uses_human_handoff(tmp_path: Path) -> None:
    install_dir = tmp_path / "Vendor"
    install_dir.mkdir()
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.LAUNCHER_AVAILABLE,
        candidates=(
            TargetCandidate(
                candidate_id="installed_diablo",
                target_id="diablo_iv",
                provider="installed_apps",
                state=TargetState.LAUNCHER_AVAILABLE,
                label="installed app metadata",
                path=str(install_dir),
                command=None,
            ),
        ),
    )

    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    assert [step.primitive_id for step in plan.steps] == ["operator.prompt.prompt"]
    assert "no safe launch command" in plan.unresolved_questions[0]
    assert "app.process.launch" not in plan.required_primitives


def test_user_memory_downgrades_volatile_running_state(tmp_path: Path) -> None:
    launcher = tmp_path / "Diablo IV.lnk"
    launcher.write_text("shortcut", encoding="utf-8")
    memory_path = tmp_path / "target-memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "targets": {
                    "diablo_iv": {
                        "label": "remembered shortcut",
                        "state": "running",
                        "path": str(launcher),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = resolve_target(
        "diablo_iv",
        providers=(UserMemoryProvider(),),
        context=TargetDiscoveryContext(memory_path=memory_path),
    )

    assert result.state is TargetState.LAUNCHABLE
    assert result.candidates[0].state is TargetState.LAUNCHABLE


def test_target_plan_json_payload_has_stable_shape() -> None:
    result = resolve_target(
        "diablo_iv",
        providers=(),
        context=TargetDiscoveryContext(),
    )
    plan = compile_target_start_plan("diablo_iv", resolution=result)
    payload = target_plan_payload(result, plan, SimpleNamespace(to_dict=lambda: {"compatibility": {"status": "ok"}}))

    assert set(payload) == {"schema_version", "resolution", "plan", "doctor"}
    assert payload["schema_version"] == "target.plan.v1"
    assert payload["resolution"]["target"]["id"] == "diablo_iv"
    assert payload["plan"]["intent"]["kind"] == "target.start"


def test_target_start_intent_compiles_through_target_resolution(monkeypatch) -> None:
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.LAUNCHABLE,
        candidates=(
            TargetCandidate(
                candidate_id="shortcut_diablo",
                target_id="diablo_iv",
                provider="start_menu_shortcut",
                state=TargetState.LAUNCHABLE,
                label="shortcut",
                path="C:/Games/Diablo IV.lnk",
                command="C:/Games/Diablo IV.lnk",
            ),
        ),
    )
    monkeypatch.setattr("ritualist.target_resolution.resolve_target", lambda _target: resolution)

    plan = compile_intent_to_plan(
        IntentSpec(
            intent_id="start_diablo",
            kind="target.start",
            display_name="Start my game",
            description="Use the target engine.",
            target="diablo_iv",
            requested_outcome="Start Diablo IV.",
            constraints={"mode": "local"},
            preferences={"focus": True},
            user_visible_summary="Start Diablo from a remembered shortcut.",
        )
    )

    assert plan.plan_id == "start_diablo"
    assert plan.intent["display_name"] == "Start my game"
    assert plan.intent["requested_outcome"] == "Start Diablo IV."
    assert plan.intent["constraints"] == {"mode": "local"}
    assert plan.intent["preferences"] == {"focus": True}
    assert plan.intent["user_visible_summary"] == "Start Diablo from a remembered shortcut."
    assert [step.primitive_id for step in plan.steps] == ["app.process.launch"]
    assert plan.steps[0].parameters["command"] == "C:/Games/Diablo IV.lnk"


def test_target_start_yaml_shorthand_compiles(tmp_path: Path, monkeypatch) -> None:
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.LAUNCHABLE,
        candidates=(
            TargetCandidate(
                candidate_id="shortcut_diablo",
                target_id="diablo_iv",
                provider="start_menu_shortcut",
                state=TargetState.LAUNCHABLE,
                label="shortcut",
                path="C:/Games/Diablo IV.lnk",
                command="C:/Games/Diablo IV.lnk",
            ),
        ),
    )
    monkeypatch.setattr("ritualist.target_resolution.resolve_target", lambda _target: resolution)
    intent_path = tmp_path / "target_start.yaml"
    intent_path.write_text(
        """
intent: target.start
target: diablo_iv
requested_outcome: Start Diablo IV.
""".lstrip(),
        encoding="utf-8",
    )

    plan = compile_plan_reference(intent_path)

    assert plan.intent["kind"] == "target.start"
    assert [step.primitive_id for step in plan.steps] == ["app.process.launch"]


def test_target_cli_discover_json_shape(monkeypatch) -> None:
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    monkeypatch.setattr(
        "ritualist.cli.resolve_target",
        lambda _target: TargetResolutionResult(
            query="diablo_iv",
            target=target,
            state=TargetState.NOT_FOUND,
            suggestions=("Choose a local executable or shortcut for this target.",),
        ),
    )

    result = CliRunner().invoke(app, ["target", "discover", "diablo_iv", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "target.resolution.v1"
    assert data["target"]["id"] == "diablo_iv"
    assert data["state"] == "not_found"
