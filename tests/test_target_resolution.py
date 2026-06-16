from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
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
    TargetMemoryRecord,
    TargetPlanSummary,
    TargetResolutionResult,
    TargetSpec,
    TargetState,
    TargetTransition,
    UserMemoryProvider,
    build_target_plan_summary,
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
            "hints": {
                "executable_names": ["Vendor.exe"],
                "window_titles": ["Vendor"],
                "launcher_hints": ["vendor_launcher"],
            },
        }
    )

    assert spec.identity.id == "vendor_app"
    assert [alias.value for alias in spec.aliases] == ["Vendor", "VA"]
    assert spec.hints.executable_names == ("Vendor.exe",)
    assert spec.hints.launcher_hints == ("vendor_launcher",)


def test_builtin_target_keeps_launcher_as_hint_not_user_action() -> None:
    target, _matched = builtin_target_catalog().resolve("diablo_iv")

    assert target is not None
    assert target.hints.launcher_hints == ("battle_net",)
    plan = compile_target_start_plan(
        "diablo_iv",
        resolution=TargetResolutionResult(
            query="diablo_iv",
            target=target,
            state=TargetState.NOT_FOUND,
        ),
    )
    assert "battle_net" not in json.dumps(plan.to_dict()).casefold()


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
    assert "installer candidate" in result.candidates[0].evidence[1]


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
    assert any("Confirm" in item or "confirmation" in item for item in plan.confirmations_needed)


def test_candidate_serialization_includes_evidence_and_transitions() -> None:
    transition = TargetTransition(
        name="ask_user",
        from_state=TargetState.INSTALL_MEDIA_PRESENT,
        to_state=TargetState.INSTALL_AVAILABLE,
        primitive_id="operator.prompt.prompt",
        requires_confirmation=True,
        summary="Ask before installer/media action.",
    )
    candidate = TargetCandidate(
        candidate_id="media_diablo",
        target_id="diablo_iv",
        provider="removable_media",
        state=TargetState.INSTALL_MEDIA_PRESENT,
        label="install media",
        possible_transitions=(transition,),
        evidence=("Found removable media",),
    )

    data = candidate.to_dict()

    assert data["possible_transitions"][0]["name"] == "ask_user"
    assert data["possible_transitions"][0]["requires_confirmation"] is True
    assert data["evidence"] == ["Found removable media"]


def test_target_memory_record_rejects_secret_fields() -> None:
    with pytest.raises(ValidationError):
        TargetMemoryRecord.model_validate(
            {
                "target_id": "diablo_iv",
                "provider_id": "user_memory",
                "path": "C:/Games/Diablo IV.lnk",
                "password": "not allowed",
            }
        )


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


def test_user_memory_ignores_secret_shaped_rows(tmp_path: Path) -> None:
    launcher = tmp_path / "Diablo IV.lnk"
    launcher.write_text("shortcut", encoding="utf-8")
    memory_path = tmp_path / "target-memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "targets": {
                    "diablo_iv": {
                        "label": "remembered shortcut",
                        "path": str(launcher),
                        "token": "not allowed",
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

    assert result.candidates == ()
    assert "ignored target memory entry containing sensitive keys" in result.diagnostics


def test_user_memory_is_preferred_over_equal_launch_sources(tmp_path: Path) -> None:
    remembered = tmp_path / "remembered.lnk"
    remembered.write_text("shortcut", encoding="utf-8")
    start_menu_shortcut = tmp_path / "start" / "Diablo IV.lnk"
    start_menu_shortcut.parent.mkdir()
    start_menu_shortcut.write_text("shortcut", encoding="utf-8")
    memory_path = tmp_path / "target-memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "targets": {
                    "diablo_iv": {
                        "label": "remembered shortcut",
                        "path": str(remembered),
                        "state": "launchable",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = resolve_target(
        "diablo_iv",
        providers=(UserMemoryProvider(), StartMenuShortcutProvider()),
        context=TargetDiscoveryContext(start_menu_roots=(start_menu_shortcut.parent,), memory_path=memory_path),
    )

    assert [candidate.provider for candidate in result.candidates[:2]] == [
        "user_memory",
        "start_menu_shortcut",
    ]
    assert result.best_candidate is not None
    assert result.best_candidate.command == str(remembered)


def test_ambiguous_equal_candidates_require_user_choice(tmp_path: Path) -> None:
    first = tmp_path / "Diablo IV.lnk"
    second = tmp_path / "Diablo IV Alt.lnk"
    first.write_text("shortcut", encoding="utf-8")
    second.write_text("shortcut", encoding="utf-8")
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
                label="Diablo IV",
                confidence=0.8,
                path=str(first),
                command=str(first),
            ),
            TargetCandidate(
                candidate_id="shortcut_diablo_alt",
                target_id="diablo_iv",
                provider="start_menu_shortcut",
                state=TargetState.LAUNCHABLE,
                label="Diablo IV Alt",
                confidence=0.78,
                path=str(second),
                command=str(second),
            ),
        ),
    )

    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    assert plan.steps == ()
    assert "Multiple possible sources found. Choose one." in plan.unresolved_questions
    assert plan.intent["target_resolution"]["selected_candidate_id"] is None


def test_plan_ranks_unsorted_candidates_before_selecting(tmp_path: Path) -> None:
    shortcut = tmp_path / "Diablo IV.lnk"
    shortcut.write_text("shortcut", encoding="utf-8")
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.LAUNCHABLE,
        candidates=(
            TargetCandidate(
                candidate_id="installed_diablo",
                target_id="diablo_iv",
                provider="installed_apps",
                state=TargetState.LAUNCHER_AVAILABLE,
                label="installed metadata",
            ),
            TargetCandidate(
                candidate_id="shortcut_diablo",
                target_id="diablo_iv",
                provider="start_menu_shortcut",
                state=TargetState.LAUNCHABLE,
                label="Diablo IV",
                path=str(shortcut),
                command=str(shortcut),
            ),
        ),
    )

    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    assert [step.primitive_id for step in plan.steps] == ["app.process.launch"]
    assert plan.steps[0].parameters["command"] == str(shortcut)
    assert plan.intent["target_resolution"]["candidate_ranking"][0]["candidate_id"] == "shortcut_diablo"


def test_target_plan_json_payload_has_stable_shape() -> None:
    result = resolve_target(
        "diablo_iv",
        providers=(),
        context=TargetDiscoveryContext(),
    )
    plan = compile_target_start_plan("diablo_iv", resolution=result)
    payload = target_plan_payload(result, plan, SimpleNamespace(to_dict=lambda: {"compatibility": {"status": "ok"}}))

    assert set(payload) == {"schema_version", "resolution", "plan", "doctor", "home_summary"}
    assert payload["schema_version"] == "target.plan.v1"
    assert payload["resolution"]["target"]["id"] == "diablo_iv"
    assert payload["plan"]["intent"]["kind"] == "target.start"
    assert payload["home_summary"]["schema_version"] == "target.plan_summary.v1"


def test_target_home_summary_reports_user_memory_source(tmp_path: Path) -> None:
    shortcut = tmp_path / "Diablo IV.lnk"
    shortcut.write_text("shortcut", encoding="utf-8")
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.LAUNCHABLE,
        candidates=(
            TargetCandidate(
                candidate_id="memory_diablo",
                target_id="diablo_iv",
                provider="user_memory",
                state=TargetState.LAUNCHABLE,
                label="remembered shortcut",
                path=str(shortcut),
                command=str(shortcut),
            ),
        ),
    )
    plan = compile_target_start_plan("diablo_iv", resolution=resolution)

    summary = build_target_plan_summary(
        resolution,
        plan,
        SimpleNamespace(compatibility="compatible_with_warnings"),
    )

    assert isinstance(summary, TargetPlanSummary)
    assert summary.last_successful_source == str(shortcut)
    assert summary.recommended_next_action == "Review the confirmation prompt before continuing."


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


def test_target_start_cli_fixture_compiles_concrete_target(monkeypatch) -> None:
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolution = TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.NOT_FOUND,
        suggestions=("Choose a local executable or shortcut for this target.",),
    )
    monkeypatch.setattr("ritualist.target_resolution.resolve_target", lambda _target: resolution)

    result = CliRunner().invoke(app, ["plan", "preview", "target.start:diablo_iv", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["plan"]["intent"]["kind"] == "target.start"
    assert data["plan"]["intent"]["target"] == "diablo_iv"
    assert data["plan"]["intent"]["target_resolution"]["state"] == "not_found"


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


def test_target_cli_plan_json_includes_home_summary(monkeypatch) -> None:
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

    result = CliRunner().invoke(app, ["target", "plan", "diablo_iv", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "target.plan.v1"
    assert data["home_summary"]["recommended_next_action"] == "no local launch source was found for Diablo IV"


def test_doctor_target_json_is_plan_doctor_and_side_effect_free(monkeypatch) -> None:
    target = builtin_target_catalog().resolve("diablo_iv")[0]

    def fail_adapter_creation():
        raise AssertionError("target doctor must not create runtime adapters")

    def fail_executor(*_args, **_kwargs):
        raise AssertionError("target doctor must not create workflow executor")

    monkeypatch.setattr("ritualist.cli.create_default_adapters", fail_adapter_creation)
    monkeypatch.setattr("ritualist.cli.WorkflowExecutor", fail_executor)
    monkeypatch.setattr(
        "ritualist.cli.resolve_target",
        lambda _target: TargetResolutionResult(
            query="diablo_iv",
            target=target,
            state=TargetState.NOT_FOUND,
            suggestions=("Choose a local executable or shortcut for this target.",),
        ),
    )

    result = CliRunner().invoke(app, ["doctor", "target:diablo_iv", "--json", "--no-strict"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "target.plan.v1"
    assert data["doctor"]["schema_version"] == "intent.plan_doctor.v1"
    assert data["doctor"]["compatibility"]["status"] == "compatible_with_warnings"
