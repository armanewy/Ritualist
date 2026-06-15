from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from ritualist.errors import PlatformUnsupportedError, RitualistError
from ritualist.models import (
    AssertBrowserTextVisibleStep,
    AssertFileExistsStep,
    AssertPathExistsStep,
    AssertProcessRunningStep,
    AssertRegistryValueStep,
    AssertWindowExistsStep,
    AssertWindowTextVisibleStep,
)

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata, WINDOWS_ONLY


class AssertFileExistsHandler:
    action_type = "assert.file_exists"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("path",),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=("file_read",),
        platform_support=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertFileExistsStep, context: ActionContext) -> str:
        path = _expand_path(step.path)
        if not _wait_until(lambda: path.is_file(), timeout_seconds=step.timeout_seconds):
            if path.exists():
                raise RitualistError(f"assert.file_exists failed: path is not a file: {path}")
            raise RitualistError(f"assert.file_exists failed: file does not exist: {path}")
        return f"file exists: {path}"


class AssertPathExistsHandler:
    action_type = "assert.path_exists"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("path",),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=("file_read",),
        platform_support=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertPathExistsStep, context: ActionContext) -> str:
        path = _expand_path(step.path)
        if not _wait_until(path.exists, timeout_seconds=step.timeout_seconds):
            raise RitualistError(f"assert.path_exists failed: path does not exist: {path}")
        return f"path exists: {path}"


class AssertProcessRunningHandler:
    action_type = "assert.process_running"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("process_name",),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=("process_inspection",),
        platform_support=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertProcessRunningStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 0
        if not context.adapters.shell.process_running(
            step.process_name,
            timeout_seconds=timeout,
        ):
            raise RitualistError(
                f"assert.process_running failed: process is not running: {step.process_name}"
            )
        return f"process is running: {step.process_name}"


class AssertWindowExistsHandler:
    action_type = "assert.window_exists"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=(),
        optional_params=("title_contains", "process_name", "timeout_seconds", "name", "optional"),
        required_capabilities=("windows_uia", "window_management"),
        platform_support=WINDOWS_ONLY,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertWindowExistsStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not context.adapters.window.window_exists(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        ):
            target = step.title_contains or step.process_name or "window"
            raise RitualistError(f"assert.window_exists failed: window not found: {target}")
        return f"window exists: {step.title_contains or step.process_name}"


class AssertWindowTextVisibleHandler:
    action_type = "assert.window_text_visible"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("window_title_contains", "text"),
        optional_params=("control_type", "exact", "timeout_seconds", "name", "optional"),
        required_capabilities=("windows_uia",),
        platform_support=WINDOWS_ONLY,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertWindowTextVisibleStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not context.adapters.desktop.text_visible(
            text=step.text,
            window_title_contains=step.window_title_contains,
            control_type=step.control_type,
            exact=step.exact,
            timeout_seconds=timeout,
        ):
            raise RitualistError(
                "assert.window_text_visible failed: visible text not found in "
                f"'{step.window_title_contains}': {step.text}"
            )
        return f"visible window text found: {step.text}"


class AssertBrowserTextVisibleHandler:
    action_type = "assert.browser_text_visible"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("text",),
        optional_params=("exact", "timeout_seconds", "name", "optional"),
        required_capabilities=("playwright", "browser_control"),
        platform_support=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertBrowserTextVisibleStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not context.adapters.browser.text_visible(
            text=step.text,
            exact=step.exact,
            timeout_seconds=timeout,
        ):
            raise RitualistError(
                f"assert.browser_text_visible failed: visible browser text not found: {step.text}"
            )
        return f"visible browser text found: {step.text}"


class AssertRegistryValueHandler:
    action_type = "assert.registry_value"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("key",),
        optional_params=("value_name", "expected_value", "timeout_seconds", "name", "optional"),
        required_capabilities=("registry_read",),
        platform_support=WINDOWS_ONLY,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AssertRegistryValueStep, context: ActionContext) -> str:
        value = _read_registry_value(step.key, step.value_name)
        if step.expected_value is not None and value != step.expected_value:
            raise RitualistError(
                "assert.registry_value failed: "
                f"{step.key}\\{step.value_name} is {value!r}, expected {step.expected_value!r}"
            )
        return f"registry value exists: {step.key}\\{step.value_name}"


def create_assertion_handlers():
    return (
        AssertFileExistsHandler(),
        AssertPathExistsHandler(),
        AssertProcessRunningHandler(),
        AssertWindowExistsHandler(),
        AssertWindowTextVisibleHandler(),
        AssertBrowserTextVisibleHandler(),
        AssertRegistryValueHandler(),
    )


def _expand_path(raw: str) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(raw))

    def replace_percent_var(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, match.group(0))

    return Path(re.sub(r"%([^%]+)%", replace_percent_var, expanded))


def _wait_until(predicate, *, timeout_seconds: float | None) -> bool:
    timeout = timeout_seconds or 0
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if timeout <= 0 or time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


def _read_registry_value(key: str, value_name: str) -> Any:
    if sys.platform != "win32":
        raise PlatformUnsupportedError("assert.registry_value is only supported on Windows")
    try:
        import winreg
    except ImportError as exc:
        raise PlatformUnsupportedError("Windows registry access is unavailable") from exc

    hive, subkey = _parse_registry_key(key, winreg)
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as handle:
            value, _value_type = winreg.QueryValueEx(handle, value_name)
            return value
    except FileNotFoundError as exc:
        raise RitualistError(
            f"assert.registry_value failed: registry value not found: {key}\\{value_name}"
        ) from exc
    except OSError as exc:
        raise RitualistError(f"assert.registry_value failed: cannot read {key}: {exc}") from exc


def _parse_registry_key(key: str, winreg_module) -> tuple[Any, str]:
    normalized = key.replace("/", "\\")
    hive_name, separator, subkey = normalized.partition("\\")
    if not separator or not subkey:
        raise RitualistError("assert.registry_value key must include a hive and subkey")
    hives = {
        "HKCU": winreg_module.HKEY_CURRENT_USER,
        "HKEY_CURRENT_USER": winreg_module.HKEY_CURRENT_USER,
        "HKLM": winreg_module.HKEY_LOCAL_MACHINE,
        "HKEY_LOCAL_MACHINE": winreg_module.HKEY_LOCAL_MACHINE,
        "HKCR": winreg_module.HKEY_CLASSES_ROOT,
        "HKEY_CLASSES_ROOT": winreg_module.HKEY_CLASSES_ROOT,
        "HKU": winreg_module.HKEY_USERS,
        "HKEY_USERS": winreg_module.HKEY_USERS,
        "HKCC": winreg_module.HKEY_CURRENT_CONFIG,
        "HKEY_CURRENT_CONFIG": winreg_module.HKEY_CURRENT_CONFIG,
    }
    hive = hives.get(hive_name.upper())
    if hive is None:
        raise RitualistError(f"assert.registry_value unsupported registry hive: {hive_name}")
    return hive, subkey.lstrip("\\")
