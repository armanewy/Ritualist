from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse
import webbrowser

from setpiece.e2e import record_event
from setpiece.errors import SetpieceError


class ShortcutKind(StrEnum):
    FOLDER = "folder"
    APP = "app"
    URL = "url"


@dataclass(frozen=True)
class ShortcutRequest:
    kind: ShortcutKind
    target: str
    title: str = ""
    component_id: str = ""
    component_type: str = ""
    app_id: str = ""

    @property
    def action_id(self) -> str:
        return "launch" if self.kind is ShortcutKind.APP else "open"


@dataclass(frozen=True)
class ShortcutResult:
    kind: ShortcutKind
    status: str
    message: str
    target_label: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status,
            "message": self.message,
            "target_label": self.target_label,
        }


FolderOpener = Callable[[Path], None]
AppLauncher = Callable[[Path], None]
UrlOpener = Callable[[str], None]


class ShortcutService:
    def __init__(
        self,
        *,
        folder_opener: FolderOpener | None = None,
        app_launcher: AppLauncher | None = None,
        url_opener: UrlOpener | None = None,
    ) -> None:
        self._folder_opener = folder_opener or _open_folder
        self._app_launcher = app_launcher or _launch_app
        self._url_opener = url_opener or _open_url

    def open(self, request: ShortcutRequest) -> ShortcutResult:
        issue = shortcut_setup_issue(request)
        if issue:
            if not _is_missing_target_issue(issue):
                raise SetpieceError(issue)
            return ShortcutResult(request.kind, "needs_setup", issue, target_label=_target_label(request))
        if request.kind is ShortcutKind.FOLDER:
            path = _local_path(request.target)
            self._folder_opener(path)
        elif request.kind is ShortcutKind.APP:
            path = _local_path(request.target)
            self._app_launcher(path)
        elif request.kind is ShortcutKind.URL:
            self._url_opener(_normalized_url(request.target))
        else:  # pragma: no cover - defensive for future enum changes.
            raise SetpieceError(f"unsupported shortcut kind: {request.kind}")
        record_event(
            "shortcut.opened",
            component_id=request.component_id,
            component_type=request.component_type,
            kind=request.kind.value,
            target_label=_target_label(request),
        )
        return ShortcutResult(
            request.kind,
            "success",
            f"{request.kind.value} shortcut opened",
            target_label=_target_label(request),
        )


def shortcut_kind_for_component(component_type: str) -> ShortcutKind | None:
    if component_type == "shortcut.folder":
        return ShortcutKind.FOLDER
    if component_type in {"shortcut.app", "app.launcher"}:
        return ShortcutKind.APP
    if component_type == "shortcut.url":
        return ShortcutKind.URL
    return None


def shortcut_request_from_component(component: Any) -> ShortcutRequest:
    kind = shortcut_kind_for_component(str(component.type))
    if kind is None:
        raise SetpieceError(f"{component.id}: component is not a shortcut")
    props = component.props_dict()
    target = _shortcut_target(kind, props, component)
    app_id = _shortcut_app_id(kind, props, component)
    title = str(props.get("title") or component.id).strip()
    return ShortcutRequest(
        kind=kind,
        target=target,
        title=title,
        component_id=str(component.id),
        component_type=str(component.type),
        app_id=app_id,
    )


def validate_shortcut_props(
    component_id: str,
    component_type: str,
    props: dict[str, object],
    *,
    imported: bool = False,
) -> tuple[list[str], list[str]]:
    kind = shortcut_kind_for_component(component_type)
    if kind is None:
        return [], []
    errors: list[str] = []
    warnings: list[str] = []
    target = _shortcut_target_from_props(kind, props)
    if not target:
        app_id = _shortcut_app_id_from_props(kind, props)
        if kind is ShortcutKind.APP and app_id:
            warnings.append(f"{component_id}: app shortcut '{app_id}' needs setup: bind a reviewed local app path")
            return errors, warnings
        warnings.append(f"{component_id}: {kind.value} shortcut target is not configured")
        return errors, warnings
    request = ShortcutRequest(
        kind=kind,
        target=target,
        component_id=component_id,
        component_type=component_type,
        app_id=_shortcut_app_id_from_props(kind, props),
    )
    issue = shortcut_setup_issue(request)
    if issue and _is_missing_target_issue(issue):
        warnings.append(f"{component_id}: {issue}")
    elif issue:
        errors.append(f"{component_id}: {issue}")
    if imported and _requires_rebinding(kind, target):
        warnings.append(f"{component_id}: imported {kind.value} shortcut requires review and rebinding")
    return errors, warnings


def shortcut_setup_issue(request: ShortcutRequest) -> str:
    target = request.target.strip()
    if not target:
        if request.kind is ShortcutKind.APP and request.app_id:
            return f"app shortcut '{request.app_id}' needs setup: bind a reviewed local app path"
        return f"{request.kind.value} shortcut target is not configured"
    if request.kind is ShortcutKind.URL:
        return _url_issue(target)
    if _looks_remote(target):
        return f"{request.kind.value} shortcut target must be local"
    if request.kind is ShortcutKind.FOLDER:
        if _has_script_or_executable_suffix(target):
            return "folder shortcut target must be a local folder, not an executable or script asset"
        path = _local_path(target)
        if not path.exists():
            return f"folder shortcut target needs setup: {path}"
        if not path.is_dir():
            return f"folder shortcut target is not a folder: {path}"
        return ""
    if request.kind is ShortcutKind.APP:
        if _looks_like_shell_command(target):
            return "app shortcut target must be a reviewed local executable or shortcut path, not a shell command"
        if _has_forbidden_app_suffix(target):
            return "app shortcut target must not be a script, installer, or command file"
        path = _local_path(target)
        if not path.exists():
            return f"app shortcut target needs setup: {path}"
        if not path.is_file():
            return f"app shortcut target is not a file: {path}"
        return ""
    return f"unsupported shortcut kind: {request.kind}"


def _shortcut_target(kind: ShortcutKind, props: dict[str, object], component: Any) -> str:
    target = _shortcut_target_from_props(kind, props)
    if target:
        return target
    binding = getattr(component, "binding", None)
    reference = getattr(binding, "reference", "") if binding is not None else ""
    binding_kind = str(getattr(binding, "kind", "") or "")
    if kind is ShortcutKind.APP and binding_kind == "app.launcher":
        return ""
    return str(reference or "").strip()


def _shortcut_app_id(kind: ShortcutKind, props: dict[str, object], component: Any) -> str:
    app_id = _shortcut_app_id_from_props(kind, props)
    if app_id:
        return app_id
    if kind is not ShortcutKind.APP:
        return ""
    binding = getattr(component, "binding", None)
    binding_kind = str(getattr(binding, "kind", "") or "")
    if binding_kind == "app.launcher":
        reference = getattr(binding, "reference", "")
        return str(reference or "").strip()
    return ""


def _shortcut_target_from_props(kind: ShortcutKind, props: dict[str, object]) -> str:
    if kind is ShortcutKind.FOLDER:
        return str(props.get("path") or props.get("folder") or "").strip()
    if kind is ShortcutKind.APP:
        return str(props.get("path") or props.get("command") or "").strip()
    if kind is ShortcutKind.URL:
        return str(props.get("url") or "").strip()
    return ""


def _shortcut_app_id_from_props(kind: ShortcutKind, props: dict[str, object]) -> str:
    if kind is ShortcutKind.APP:
        return str(props.get("app_id") or "").strip()
    return ""


def _url_issue(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return "URL shortcut target must use http or https"
    if parsed.username or parsed.password:
        return "URL shortcut target must not include credentials"
    return ""


def _normalized_url(value: str) -> str:
    issue = _url_issue(value)
    if issue:
        raise SetpieceError(issue)
    return value.strip()


def _local_path(value: str) -> Path:
    return Path(value).expanduser()


def _looks_remote(value: str) -> bool:
    text = value.strip()
    return "://" in text or text.startswith("\\\\") or text.startswith("//")


def _looks_like_shell_command(value: str) -> bool:
    text = value.strip().casefold()
    shell_markers = ("&&", "||", "|", ">", "<", "\n", "\r", "`")
    shell_names = ("cmd /", "cmd.exe", "powershell", "pwsh", "bash ", "sh ")
    return any(marker in value for marker in shell_markers) or any(name in text for name in shell_names)


def _has_script_or_executable_suffix(value: str) -> bool:
    suffix = Path(value).suffix.casefold()
    return suffix in {
        ".bat",
        ".cmd",
        ".com",
        ".exe",
        ".js",
        ".mjs",
        ".msi",
        ".ps1",
        ".py",
        ".scr",
        ".sh",
        ".url",
        ".vbs",
    }


def _has_forbidden_app_suffix(value: str) -> bool:
    suffix = Path(value).suffix.casefold()
    return suffix in {
        ".bat",
        ".cmd",
        ".com",
        ".js",
        ".mjs",
        ".msi",
        ".ps1",
        ".py",
        ".scr",
        ".sh",
        ".url",
        ".vbs",
    }


def _requires_rebinding(kind: ShortcutKind, target: str) -> bool:
    if kind is ShortcutKind.URL:
        return False
    path = Path(target).expanduser()
    return path.is_absolute()


def _is_missing_target_issue(issue: str) -> bool:
    return "needs setup" in issue or "not configured" in issue


def _target_label(request: ShortcutRequest) -> str:
    if request.kind is ShortcutKind.URL:
        parsed = urlparse(request.target)
        return parsed.netloc or request.target
    if request.target:
        return Path(request.target).name or request.target
    if request.app_id:
        return request.app_id
    return request.title or request.component_id


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])


def _launch_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    subprocess.Popen([str(path)])


def _open_url(url: str) -> None:
    webbrowser.open(url)
