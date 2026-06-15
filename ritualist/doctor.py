from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass

from .adapters.shell import resolve_local_command_path
from .models import Recipe
from .paths import browser_profiles_dir


@dataclass(frozen=True)
class DoctorCheck:
    status: str
    name: str
    message: str


def diagnose_recipe(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = [
        DoctorCheck("ok", "recipe", f"loaded {recipe.id} ({recipe.name})"),
    ]
    action_types = {step.action for step in recipe.execution_steps}

    if any(action.startswith("browser.") or action == "assert.browser_text_visible" for action in action_types):
        checks.extend(_check_playwright())
        checks.extend(_check_browser_profiles(recipe))
        if "assert.browser_text_visible" in action_types and "browser.open" not in action_types:
            checks.append(
                DoctorCheck(
                    "warn",
                    "assert.browser_text_visible",
                    "browser text assertions require a prior browser.open step in the run",
                )
            )

    if "app.wait_process" in action_types or "assert.process_running" in action_types:
        checks.append(_check_import("psutil", "psutil", "install ritualist[windows]"))

    if any(
        action.startswith("window.")
        or action.startswith("desktop.")
        or action in {"assert.window_exists", "assert.window_text_visible"}
        for action in action_types
    ):
        if sys.platform != "win32":
            checks.append(
                DoctorCheck(
                    "warn",
                    "windows",
                    "window and desktop UI Automation actions are supported only on Windows",
                )
            )
        else:
            checks.append(_check_import("pywinauto", "pywinauto", "install ritualist[windows]"))

    if "assert.registry_value" in action_types:
        if sys.platform != "win32":
            checks.append(
                DoctorCheck("warn", "windows", "assert.registry_value is supported only on Windows")
            )
        else:
            checks.append(DoctorCheck("ok", "registry", "Windows registry checks are available"))

    if "input.hotkey" in action_types:
        if sys.platform != "win32":
            checks.append(
                DoctorCheck("warn", "windows", "input.hotkey is supported only on Windows")
            )
        else:
            checks.append(_check_import("pywinauto", "pywinauto", "install ritualist[windows]"))

    checks.extend(_check_app_launch_paths(recipe))
    checks.extend(_describe_desktop_clicks(recipe))
    checks.extend(_describe_assertions(recipe))
    return checks


def _check_playwright() -> list[DoctorCheck]:
    if not _module_available("playwright.sync_api"):
        return [
            DoctorCheck(
                "error",
                "playwright",
                "Playwright import failed; install ritualist[browser] and run "
                "'python -m playwright install chromium'",
            )
        ]
    return [DoctorCheck("ok", "playwright", "Playwright import works")]


def _check_browser_profiles(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for step in recipe.steps:
        if step.action != "browser.open":
            continue
        path = browser_profiles_dir() / step.browser / step.profile
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            checks.append(
                DoctorCheck("error", "browser-profile", f"cannot create {path}: {exc}")
            )
        else:
            checks.append(DoctorCheck("ok", "browser-profile", f"can use {path}"))
    return checks


def _check_import(module: str, name: str, install_hint: str) -> DoctorCheck:
    if not _module_available(module):
        return DoctorCheck("error", name, f"{name} import failed; {install_hint}")
    return DoctorCheck("ok", name, f"{name} import works")


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _check_app_launch_paths(recipe: Recipe) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for step in recipe.steps:
        if step.action != "app.launch":
            continue
        path = resolve_local_command_path(step.command)
        if path is None:
            checks.append(
                DoctorCheck("ok", "app.launch", f"command will be resolved by the OS: {step.command}")
            )
            continue
        if path.exists():
            checks.append(DoctorCheck("ok", "app.launch", f"path exists: {path}"))
        else:
            checks.append(
                DoctorCheck(
                    "error",
                    "app.launch",
                    "path does not exist: "
                    f"{path}. Edit the recipe variable or config for this app path.",
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
                )
            )
        elif step.action == "assert.window_exists":
            checks.append(
                DoctorCheck(
                    "info",
                    step.action,
                    f"target window contains '{step.title_contains or ''}' process '{step.process_name or ''}'",
                )
            )
        elif step.action == "assert.browser_text_visible":
            checks.append(DoctorCheck("info", step.action, f"visible browser text '{step.text}'"))
        elif step.action in {"assert.file_exists", "assert.path_exists"}:
            checks.append(DoctorCheck("info", step.action, f"path '{step.path}'"))
        elif step.action == "assert.process_running":
            checks.append(DoctorCheck("info", step.action, f"process '{step.process_name}'"))
        elif step.action == "assert.registry_value":
            checks.append(DoctorCheck("info", step.action, f"registry value '{step.key}\\{step.value_name}'"))
    return checks
