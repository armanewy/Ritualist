from __future__ import annotations

from pathlib import Path

import pytest

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasRuntimeContext,
    CanvasRuntimeController,
    build_canvas_runtime_model,
    create_component_registry,
    normalize_canvas_bindings,
    validate_canvas_document,
    validate_canvas_structure,
)
from ritualist.errors import RitualistError
from ritualist.shortcuts import ShortcutResult


class _FailingActionService:
    calls: list[object] = []

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"shortcut dispatch must not touch HomeActionService.{name}")


class _FakeShortcutService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def open(self, request: object) -> ShortcutResult:
        kind = getattr(request, "kind")
        target = str(getattr(request, "target"))
        action_id = str(getattr(request, "action_id"))
        self.calls.append((str(kind.value), action_id, target))
        return ShortcutResult(kind, "success", "fake shortcut opened", target_label=Path(target).name or target)


def _shortcut_canvas(component: CanvasComponent) -> CanvasDocument:
    return CanvasDocument(
        id="shortcut_canvas",
        name="Shortcut Canvas",
        components=(component,),
    )


def _folder_component(path: Path | str) -> CanvasComponent:
    return CanvasComponent(
        id="folder",
        type="shortcut.folder",
        width=240,
        height=96,
        props={"title": "Folder", "path": str(path)},
    )


def _app_component(path: Path | str, *, type_id: str = "shortcut.app") -> CanvasComponent:
    return CanvasComponent(
        id="app",
        type=type_id,
        width=240,
        height=96,
        props={"title": "App", "path": str(path)},
    )


def _url_component(url: str) -> CanvasComponent:
    return CanvasComponent(
        id="url",
        type="shortcut.url",
        width=240,
        height=96,
        props={"title": "Docs", "url": url},
    )


def _legacy_app_id_launcher(app_id: str = "project_editor") -> CanvasComponent:
    return CanvasComponent(
        id="legacy",
        type="app.launcher",
        width=240,
        height=96,
        props={"title": "Legacy Launcher", "app_id": app_id},
        binding=CanvasComponentBinding(kind=CanvasBindingKind.APP_LAUNCHER, id=app_id),
    )


def test_shortcut_component_registry_and_legacy_launcher_actions_are_registered() -> None:
    registry = create_component_registry()

    assert registry.get("shortcut.folder").actions == ("open",)
    assert registry.get("shortcut.app").actions == ("launch",)
    assert registry.get("shortcut.url").actions == ("open",)
    assert registry.get("app.launcher").actions == ("launch",)
    assert CanvasBindingKind.SHORTCUT_FOLDER in registry.get("shortcut.folder").supported_bindings
    assert CanvasBindingKind.SHORTCUT_APP in registry.get("app.launcher").supported_bindings


def test_shortcut_runtime_exposes_instant_actions_without_ritual_controls(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    canvas = _shortcut_canvas(_folder_component(folder))

    model = build_canvas_runtime_model(canvas, context=CanvasRuntimeContext(recent_runs=()))
    state = model.component_state("folder")

    assert state.state == "ready"
    assert state.enabled_actions == ("open",)
    assert "run" not in state.enabled_actions
    assert state.data["shortcut"]["kind"] == "folder"


def test_missing_shortcut_target_is_needs_setup_not_crash(tmp_path: Path) -> None:
    missing = tmp_path / "missing-folder"
    canvas = _shortcut_canvas(_folder_component(missing))

    validation = validate_canvas_structure(canvas)
    model = build_canvas_runtime_model(canvas, context=CanvasRuntimeContext(recent_runs=()))
    state = model.component_state("folder")

    assert validation.valid
    assert any("needs setup" in warning for warning in validation.warnings)
    assert state.state == "needs_setup"
    assert state.status == "warning"
    assert state.enabled_actions == ()
    assert state.disabled_actions == ("open",)


def test_shortcut_folder_dispatch_uses_fake_and_creates_no_run_log(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    shortcut_service = _FakeShortcutService()
    controller = CanvasRuntimeController(
        action_service=_FailingActionService(),  # type: ignore[arg-type]
        shortcut_service=shortcut_service,  # type: ignore[arg-type]
    )

    result = controller.dispatch(_shortcut_canvas(_folder_component(folder)), "folder", "open")

    assert result.ok
    assert result.data["shortcut"]["kind"] == "folder"
    assert shortcut_service.calls == [("folder", "open", str(folder))]
    assert not (tmp_path / "runs").exists()


def test_shortcut_url_dispatch_uses_http_https_only() -> None:
    shortcut_service = _FakeShortcutService()
    controller = CanvasRuntimeController(shortcut_service=shortcut_service)  # type: ignore[arg-type]

    result = controller.dispatch(_shortcut_canvas(_url_component("https://example.com/docs")), "url", "open")
    bad = validate_canvas_structure(_shortcut_canvas(_url_component("javascript:alert(1)")))

    assert result.ok
    assert shortcut_service.calls == [("url", "open", "https://example.com/docs")]
    assert not bad.valid
    assert any("http or https" in error for error in bad.errors)


def test_shortcut_app_and_legacy_launcher_dispatch_through_same_fake(tmp_path: Path) -> None:
    app = tmp_path / "editor.exe"
    app.write_text("fake executable placeholder", encoding="utf-8")
    shortcut_service = _FakeShortcutService()
    controller = CanvasRuntimeController(shortcut_service=shortcut_service)  # type: ignore[arg-type]

    app_result = controller.dispatch(_shortcut_canvas(_app_component(app)), "app", "launch")
    legacy_result = controller.dispatch(
        _shortcut_canvas(_app_component(app, type_id="app.launcher")),
        "app",
        "launch",
    )

    assert app_result.ok and legacy_result.ok
    assert shortcut_service.calls == [
        ("app", "launch", str(app)),
        ("app", "launch", str(app)),
    ]


def test_legacy_app_id_launcher_is_compatible_needs_setup_not_path_execution() -> None:
    canvas = _shortcut_canvas(_legacy_app_id_launcher())
    validation = validate_canvas_structure(canvas)
    model = build_canvas_runtime_model(canvas, context=CanvasRuntimeContext(recent_runs=()))
    state = model.component_state("legacy")
    controller = CanvasRuntimeController()

    result = controller.dispatch(canvas, "legacy", "launch")

    assert validation.valid
    assert any("bind a reviewed local app path" in warning for warning in validation.warnings)
    assert state.state == "needs_setup"
    assert state.enabled_actions == ()
    assert state.disabled_actions == ("launch",)
    assert state.data["shortcut"]["target_label"] == "project_editor"
    assert result.status == "needs_setup"
    assert result.data["shortcut"]["target_label"] == "project_editor"


def test_remote_and_script_like_shortcut_targets_are_rejected(tmp_path: Path) -> None:
    script = tmp_path / "setup.ps1"
    script.write_text("Write-Host unsafe", encoding="utf-8")

    remote_folder = validate_canvas_structure(_shortcut_canvas(_folder_component(r"\\server\share")))
    script_folder = validate_canvas_structure(_shortcut_canvas(_folder_component(script)))
    shell_app = validate_canvas_structure(_shortcut_canvas(_app_component("cmd /c calc.exe")))
    script_app = validate_canvas_structure(_shortcut_canvas(_app_component(script)))
    url_shortcut = tmp_path / "bad.url"
    url_shortcut.write_text("[InternetShortcut]\nURL=javascript:alert(1)\n", encoding="utf-8")
    url_file_app = validate_canvas_structure(_shortcut_canvas(_app_component(url_shortcut)))

    assert not remote_folder.valid
    assert any("must be local" in error for error in remote_folder.errors)
    assert not script_folder.valid
    assert any("not an executable or script" in error for error in script_folder.errors)
    assert not shell_app.valid
    assert any("not a shell command" in error for error in shell_app.errors)
    assert not script_app.valid
    assert any("must not be a script" in error for error in script_app.errors)
    assert not url_file_app.valid
    assert any("must not be a script" in error for error in url_file_app.errors)


def test_imported_absolute_shortcuts_require_review_without_auto_run(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    app = tmp_path / "editor.exe"
    app.write_text("fake executable placeholder", encoding="utf-8")
    canvas = CanvasDocument(
        id="imported_shortcuts",
        name="Imported Shortcuts",
        components=(
            _folder_component(folder),
            _app_component(app),
            _url_component("https://example.com/docs"),
        ),
    )

    result = validate_canvas_document(canvas, imported=True)

    assert result.valid
    assert any("folder shortcut requires review and rebinding" in warning for warning in result.warnings)
    assert any("app shortcut requires review and rebinding" in warning for warning in result.warnings)
    assert not any("auto-run" in warning.casefold() for warning in result.warnings)


def test_shortcuts_reject_auto_run_and_arbitrary_action_strings(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    canvas = _shortcut_canvas(
        CanvasComponent(
            id="folder",
            type="shortcut.folder",
            width=240,
            height=96,
            props={"title": "Folder", "path": str(folder), "auto_run": True},
        )
    )
    controller = CanvasRuntimeController(shortcut_service=_FakeShortcutService())  # type: ignore[arg-type]

    result = validate_canvas_structure(canvas)

    assert not result.valid
    assert any("auto-run" in error for error in result.errors)
    with pytest.raises(RitualistError, match="unsupported"):
        controller.dispatch(_shortcut_canvas(_folder_component(folder)), "folder", "shell")


def test_normalize_canvas_bindings_infers_typed_shortcut_bindings(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    app = tmp_path / "editor.exe"
    canvas = CanvasDocument(
        id="legacy_shortcuts",
        name="Legacy Shortcuts",
        components=(
            _folder_component(folder),
            _app_component(app),
            _url_component("https://example.com/docs"),
        ),
    )

    normalized = normalize_canvas_bindings(canvas)
    bindings = {component.id: component.binding for component in normalized.components}

    assert bindings["folder"] == CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_FOLDER, path=str(folder))
    assert bindings["app"] == CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_APP, path=str(app))
    assert bindings["url"] == CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_URL, url="https://example.com/docs")
