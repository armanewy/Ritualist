from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from .actions.metadata import ActionMetadata
from .actions.registry import ActionRegistry, create_default_registry
from .adapters.shell import resolve_local_command_path
from .models import Recipe
from .paths import browser_profiles_dir


@dataclass(frozen=True)
class DoctorCheck:
    status: str
    name: str
    message: str
    section: str = "General"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "category": self.section,
            "status": _json_status(self.status),
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class DoctorReport:
    recipe_id: str
    recipe_name: str
    current_os: str
    checks: list[DoctorCheck]
    action_metadata: list[ActionMetadata]
    recipe: Recipe
    missing_variables: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    schema_version: str = "doctor.v2"

    @property
    def errors_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "error")

    @property
    def warnings_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "warn")

    @property
    def compatibility(self) -> str:
        if self.errors_count:
            return "incompatible"
        if self.warnings_count:
            return "compatible_with_warnings"
        return "compatible"

    @property
    def compatibility_score(self) -> int:
        return max(0, 100 - self.errors_count * 25 - self.warnings_count * 10)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recipe_id": self.recipe_id,
            "recipe_name": self.recipe_name,
            "compatibility": {
                "status": self.compatibility,
                "errors_count": self.errors_count,
                "warnings_count": self.warnings_count,
            },
            "checks": [check.to_dict() for check in self.checks],
            "capabilities": self._capabilities_to_dict(),
            "variables": self._variables_to_dict(),
            "actions": [metadata.to_dict() for metadata in self.action_metadata],
            "environment": self._environment_to_dict(),
        }

    def _capabilities_to_dict(self) -> list[dict[str, Any]]:
        capability_checks = {
            check.details.get("capability", check.name): check
            for check in self.checks
            if check.section == "Capabilities"
        }
        rows: list[dict[str, Any]] = []
        for capability in self.required_capabilities:
            check = capability_checks.get(capability)
            rows.append(
                {
                    "id": capability,
                    "status": _json_status(check.status) if check else "ok",
                    "message": check.message if check else "capability is declared",
                    "details": check.details if check else {"capability": capability},
                }
            )
        return rows

    def _variables_to_dict(self) -> list[dict[str, Any]]:
        missing_roots = {item.split(".", 1)[0] for item in self.missing_variables}
        names = sorted(set(self.recipe.variables) | set(self.missing_variables) | missing_roots)
        rows: list[dict[str, Any]] = []
        for name in names:
            hint = self.recipe.environment.variable_hints.get(name)
            status = (
                "missing"
                if name in self.missing_variables or name in missing_roots
                else "configured"
            )
            rows.append(
                {
                    "name": name,
                    "status": status,
                    "details": {
                        "has_recipe_default": name in self.recipe.variables,
                        "hint": hint,
                    },
                }
            )
        return rows

    def _environment_to_dict(self) -> dict[str, Any]:
        environment = self.recipe.environment
        return {
            "current_os": self.current_os,
            "expected_os": list(environment.os),
            "required_capabilities": list(environment.required_capabilities),
            "expected_windows": [
                expected.model_dump(mode="json") for expected in environment.expected_windows
            ],
            "expected_labels": [
                expected.model_dump(mode="json") for expected in environment.expected_labels
            ],
            "variable_hints": dict(sorted(environment.variable_hints.items())),
        }


def _json_status(status: str) -> str:
    if status == "warn":
        return "warning"
    if status == "info":
        return "ok"
    return status


def diagnose_recipe(
    recipe: Recipe,
    *,
    missing_variables: list[str] | None = None,
    registry: ActionRegistry | None = None,
) -> list[DoctorCheck]:
    return build_doctor_report(
        recipe,
        missing_variables=missing_variables,
        registry=registry,
    ).checks


def build_doctor_report(
    recipe: Recipe,
    *,
    missing_variables: list[str] | None = None,
    registry: ActionRegistry | None = None,
) -> DoctorReport:
    registry = registry or create_default_registry()
    current_os = _current_os()
    action_types = sorted({step.action for step in recipe.execution_steps})
    checks: list[DoctorCheck] = [
        DoctorCheck(
            "ok",
            "recipe",
            f"loaded {recipe.id} ({recipe.name})",
            section="General",
        )
    ]

    checks.extend(_check_environment_os(recipe, current_os))
    checks.extend(_check_variables(recipe, missing_variables or []))
    checks.extend(_check_actions(action_types, registry, current_os))

    required_capabilities = _required_capabilities(recipe, action_types, registry)
    capability_checks = [_check_capability(capability) for capability in required_capabilities]
    checks.extend(capability_checks)

    checks.extend(_check_browser_profiles(recipe))
    checks.extend(_check_app_launch_paths(recipe))
    checks.extend(_describe_desktop_clicks(recipe))
    checks.extend(_describe_assertions(recipe))
    checks.extend(_check_expected_windows(recipe))
    checks.extend(_check_expected_labels(recipe))
    checks.extend(_check_browser_assertion_flow(action_types))
    checks.extend(_describe_import_pack_policy(action_types, registry))

    return DoctorReport(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        current_os=current_os,
        checks=checks,
        action_metadata=[registry.metadata(action_type) for action_type in action_types],
        recipe=recipe,
        missing_variables=sorted(missing_variables or []),
        required_capabilities=required_capabilities,
    )


def _check_environment_os(recipe: Recipe, current_os: str) -> list[DoctorCheck]:
    expected = recipe.environment.os
    if not expected:
        return [
            DoctorCheck(
                "info",
                "os",
                f"recipe does not restrict OS; current OS is {current_os}",
                section="Capabilities",
                details={"current_os": current_os},
            )
        ]
    if current_os in expected:
        return [
            DoctorCheck(
                "ok",
                "os",
                f"current OS {current_os} is allowed",
                section="Capabilities",
                details={"current_os": current_os, "expected": expected},
            )
        ]
    return [
        DoctorCheck(
            "error",
            "os",
            f"recipe expects OS {', '.join(expected)}; current OS is {current_os}",
            section="Capabilities",
            details={"current_os": current_os, "expected": expected},
        )
    ]


def _check_variables(recipe: Recipe, missing_variables: list[str]) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for name in sorted(missing_variables):
        hint = recipe.environment.variable_hints.get(name) or recipe.environment.variable_hints.get(
            name.split(".", 1)[0]
        )
        message = (
            f"missing variable '{name}'. Provide --var {name}=value or add variables.{name} "
            "to the recipe/config."
        )
        if hint:
            message = f"{message} Hint: {hint}"
        checks.append(
            DoctorCheck(
                "error",
                name,
                message,
                section="Variables",
                details={"variable": name, "hint": hint},
            )
        )
    for name in sorted(recipe.variables):
        if name in {item.split(".", 1)[0] for item in missing_variables}:
            continue
        checks.append(
            DoctorCheck(
                "ok",
                name,
                "variable is configured",
                section="Variables",
                details={"variable": name},
            )
        )
    if not checks:
        checks.append(
            DoctorCheck(
                "info",
                "variables",
                "recipe declares no template variables",
                section="Variables",
            )
        )
    return checks


def _check_actions(
    action_types: list[str],
    registry: ActionRegistry,
    current_os: str,
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for action_type in action_types:
        try:
            metadata = registry.metadata(action_type)
        except KeyError:
            checks.append(
                DoctorCheck(
                    "error",
                    action_type,
                    "no action handler metadata is registered",
                    section="Actions",
                )
            )
            continue
        if current_os not in metadata.platform_support:
            checks.append(
                DoctorCheck(
                    "error",
                    action_type,
                    "action is not supported on "
                    f"{current_os}; supported platforms: {', '.join(metadata.platform_support)}",
                    section="Actions",
                    details=metadata.to_dict(),
                )
            )
            continue
        checks.append(
            DoctorCheck(
                "ok",
                action_type,
                f"supported on {current_os}; side effect: {metadata.side_effect_level}",
                section="Actions",
                details=metadata.to_dict(),
            )
        )
    return checks


def _required_capabilities(
    recipe: Recipe,
    action_types: list[str],
    registry: ActionRegistry,
) -> list[str]:
    capabilities: set[str] = set(recipe.environment.required_capabilities)
    for action_type in action_types:
        try:
            capabilities.update(registry.metadata(action_type).required_capabilities)
        except KeyError:
            continue
    return sorted(capabilities)


def _check_capability(capability: str) -> DoctorCheck:
    if capability == "playwright":
        return _check_import(
            "playwright.sync_api",
            "playwright",
            "install ritualist[browser] and run 'python -m playwright install chromium'",
        )
    if capability == "browser_control":
        return _check_import(
            "playwright.sync_api",
            "browser_control",
            "install ritualist[browser] and run 'python -m playwright install chromium'",
        )
    if capability == "windows_uia":
        if sys.platform != "win32":
            return DoctorCheck(
                "error",
                capability,
                "Windows UI Automation requires Windows and pywinauto; install ritualist[windows]",
                section="Capabilities",
                details={"capability": capability},
            )
        return _check_import("pywinauto", capability, "install ritualist[windows]")
    if capability == "window_management":
        if sys.platform != "win32":
            return DoctorCheck(
                "error",
                capability,
                "window management requires Windows UI Automation; install ritualist[windows]",
                section="Capabilities",
                details={"capability": capability},
            )
        return _check_window_management_capability()
    if capability == "keyboard_input":
        if sys.platform != "win32":
            return DoctorCheck(
                "error",
                capability,
                "keyboard input requires Windows UI Automation; install ritualist[windows]",
                section="Capabilities",
                details={"capability": capability},
            )
        return _check_import("pywinauto", capability, "install ritualist[windows]")
    if capability == "app_launch":
        return DoctorCheck(
            "ok",
            capability,
            "local app launch is available through the OS",
            section="Capabilities",
            details={"capability": capability},
        )
    if capability == "file_read":
        return DoctorCheck(
            "ok",
            capability,
            "local filesystem read checks are available",
            section="Capabilities",
            details={"capability": capability},
        )
    if capability == "file_write":
        writable = os.access(os.getcwd(), os.W_OK)
        return DoctorCheck(
            "ok" if writable else "error",
            capability,
            "current directory is writable" if writable else "current directory is not writable",
            section="Capabilities",
            details={"capability": capability},
        )
    if capability == "registry_read":
        if sys.platform != "win32":
            return DoctorCheck(
                "error",
                capability,
                "registry read requires Windows",
                section="Capabilities",
                details={"capability": capability},
            )
        return DoctorCheck(
            "ok",
            capability,
            "Windows registry read APIs are available",
            section="Capabilities",
            details={"capability": capability},
        )
    if capability == "registry_write":
        if sys.platform != "win32":
            return DoctorCheck(
                "error",
                capability,
                "registry write requires Windows",
                section="Capabilities",
                details={"capability": capability},
            )
        return DoctorCheck(
            "ok",
            capability,
            "Windows registry write APIs are available",
            section="Capabilities",
            details={"capability": capability},
        )
    if capability == "process_inspection":
        check = _check_import("psutil", "psutil", "install ritualist[windows]")
        return DoctorCheck(
            check.status,
            capability,
            check.message,
            section=check.section,
            details={"module": "psutil", "capability": capability},
        )
    return DoctorCheck(
        "error",
        capability,
        "unknown capability requested by recipe",
        section="Capabilities",
        details={"capability": capability},
    )


def _check_import(module: str, name: str, install_hint: str) -> DoctorCheck:
    display_name = "Playwright" if name == "playwright" else name
    if not _module_available(module):
        return DoctorCheck(
            "error",
            name,
            f"{display_name} import failed; {install_hint}",
            section="Capabilities",
            details={"module": module},
        )
    return DoctorCheck(
        "ok",
        name,
        f"{display_name} import works",
        section="Capabilities",
        details={"module": module},
    )


def _check_window_management_capability() -> DoctorCheck:
    pywinauto_check = _check_import("pywinauto", "window_management", "install ritualist[windows]")
    if pywinauto_check.status != "ok":
        return pywinauto_check
    if not _module_available("win32api"):
        return DoctorCheck(
            "error",
            "window_management",
            "window_management import failed; install ritualist[windows] (pywin32/win32api missing)",
            section="Capabilities",
            details={"module": "win32api", "capability": "window_management"},
        )
    return DoctorCheck(
        "ok",
        "window_management",
        "window_management imports work",
        section="Capabilities",
        details={"modules": ["pywinauto", "win32api"], "capability": "window_management"},
    )


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _check_browser_profiles(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for step in recipe.steps:
        if step.action != "browser.open":
            continue
        path = browser_profiles_dir() / step.browser / step.profile
        parent = _nearest_existing_parent(path)
        if parent is not None and os.access(parent, os.W_OK):
            checks.append(
                DoctorCheck(
                    "ok",
                    "browser-profile",
                    f"profile path parent is writable: {path}",
                    section="App paths",
                    details={"path": str(path)},
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "error",
                    "browser-profile",
                    f"browser profile path is not writable: {path}",
                    section="App paths",
                    details={"path": str(path)},
                )
            )
    return checks


def _nearest_existing_parent(path) -> Any:
    current = path
    while current != current.parent:
        if current.exists():
            return current if current.is_dir() else current.parent
        current = current.parent
    return current if current.exists() else None


def _check_app_launch_paths(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for step in recipe.steps:
        if step.action != "app.launch":
            continue
        path = resolve_local_command_path(step.command)
        if path is None:
            checks.append(
                DoctorCheck(
                    "ok",
                    "app.launch",
                    f"command will be resolved by the OS: {step.command}",
                    section="App paths",
                    details={"command": step.command},
                )
            )
            continue
        if path.exists():
            checks.append(
                DoctorCheck(
                    "ok",
                    "app.launch",
                    f"path exists: {path}",
                    section="App paths",
                    details={"path": str(path)},
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "error",
                    "app.launch",
                    "path does not exist: "
                    f"{path}. Edit the recipe variable or config for this app path.",
                    section="App paths",
                    details={"path": str(path)},
                )
            )
    return checks


def _describe_desktop_clicks(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for step in recipe.execution_steps:
        if step.action != "desktop.click_text":
            continue
        checks.append(
            DoctorCheck(
                "info",
                "desktop.click_text",
                f"target window contains '{step.window_title_contains}', click text '{step.text}'",
                section="Windows/UI labels",
                details={
                    "window_title_contains": step.window_title_contains,
                    "text": step.text,
                },
            )
        )
    return checks


def _describe_assertions(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for step in recipe.execution_steps:
        if not step.action.startswith("assert."):
            continue
        if step.action == "assert.window_text_visible":
            checks.append(
                DoctorCheck(
                    "info",
                    step.action,
                    f"target window contains '{step.window_title_contains}', visible text '{step.text}'",
                    section="Windows/UI labels",
                )
            )
        elif step.action == "assert.window_exists":
            checks.append(
                DoctorCheck(
                    "info",
                    step.action,
                    f"target window contains '{step.title_contains or ''}' process '{step.process_name or ''}'",
                    section="Windows/UI labels",
                )
            )
        elif step.action == "assert.browser_text_visible":
            checks.append(
                DoctorCheck(
                    "info",
                    step.action,
                    f"visible browser text '{step.text}'",
                    section="Windows/UI labels",
                )
            )
        elif step.action in {"assert.file_exists", "assert.path_exists"}:
            checks.append(
                DoctorCheck("info", step.action, f"path '{step.path}'", section="App paths")
            )
        elif step.action == "assert.process_running":
            checks.append(
                DoctorCheck(
                    "info",
                    step.action,
                    f"process '{step.process_name}'",
                    section="Capabilities",
                )
            )
        elif step.action == "assert.registry_value":
            checks.append(
                DoctorCheck(
                    "info",
                    step.action,
                    f"registry value '{step.key}\\{step.value_name}'",
                    section="Capabilities",
                )
            )
    return checks


def _check_expected_windows(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for expected in recipe.environment.expected_windows:
        target = expected.title_contains or expected.process_name or "window"
        if sys.platform != "win32":
            checks.append(
                DoctorCheck(
                    "warn",
                    "expected_window",
                    f"cannot inspect expected window '{target}' on {_current_os()}",
                    section="Windows/UI labels",
                )
            )
            continue
        if not _module_available("pywinauto"):
            checks.append(
                DoctorCheck(
                    "warn",
                    "expected_window",
                    f"cannot inspect expected window '{target}'; install ritualist[windows]",
                    section="Windows/UI labels",
                )
            )
            continue
        try:
            from .adapters.window_manager import WindowsWindowManager

            exists = WindowsWindowManager().window_exists(
                title_contains=expected.title_contains,
                process_name=expected.process_name,
                timeout_seconds=1.0,
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic probe must stay best-effort.
            checks.append(
                DoctorCheck(
                    "warn",
                    "expected_window",
                    f"could not inspect expected window '{target}': {exc}",
                    section="Windows/UI labels",
                )
            )
            continue
        checks.append(
            DoctorCheck(
                "ok" if exists else "warn",
                "expected_window",
                f"expected window {'found' if exists else 'not currently visible'}: {target}",
                section="Windows/UI labels",
                details={"target": target},
            )
        )
    return checks


def _check_expected_labels(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for expected in recipe.environment.expected_labels:
        if sys.platform != "win32":
            checks.append(
                DoctorCheck(
                    "warn",
                    "expected_label",
                    "cannot inspect expected label "
                    f"'{expected.text}' in '{expected.window_title_contains}' on {_current_os()}",
                    section="Windows/UI labels",
                )
            )
            continue
        if not _module_available("pywinauto"):
            checks.append(
                DoctorCheck(
                    "warn",
                    "expected_label",
                    "cannot inspect expected label "
                    f"'{expected.text}' in '{expected.window_title_contains}'; install ritualist[windows]",
                    section="Windows/UI labels",
                )
            )
            continue
        try:
            from .adapters.windows_uia import WindowsUIAutomationAdapter

            visible = WindowsUIAutomationAdapter().text_visible(
                text=expected.text,
                window_title_contains=expected.window_title_contains,
                control_type=expected.control_type,
                exact=expected.exact,
                timeout_seconds=1.0,
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic probe must stay best-effort.
            checks.append(
                DoctorCheck(
                    "warn",
                    "expected_label",
                    "could not inspect expected label "
                    f"'{expected.text}' in '{expected.window_title_contains}': {exc}",
                    section="Windows/UI labels",
                )
            )
            continue
        checks.append(
            DoctorCheck(
                "ok" if visible else "warn",
                "expected_label",
                "expected label "
                f"{'found' if visible else 'not currently visible'}: "
                f"'{expected.text}' in '{expected.window_title_contains}'",
                section="Windows/UI labels",
                details={
                    "window_title_contains": expected.window_title_contains,
                    "text": expected.text,
                },
            )
        )
    return checks


def _check_browser_assertion_flow(action_types: list[str]) -> list[DoctorCheck]:
    if "assert.browser_text_visible" not in action_types or "browser.open" in action_types:
        return []
    return [
        DoctorCheck(
            "warn",
            "assert.browser_text_visible",
            "browser text assertions require a prior browser.open step in the run",
            section="Actions",
        )
    ]


def _describe_import_pack_policy(
    action_types: list[str],
    registry: ActionRegistry,
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for action_type in action_types:
        metadata = registry.metadata(action_type)
        if metadata.allowed_in_imported_packs:
            continue
        checks.append(
            DoctorCheck(
                "info",
                action_type,
                "action is disabled by default for imported recipe packs",
                section="Safety",
                details={
                    "allowed_in_imported_packs": False,
                    "side_effect_level": metadata.side_effect_level,
                    "confirmation_policy": metadata.confirmation_policy,
                },
            )
        )
    return checks


def _current_os() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform
