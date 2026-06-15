from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .paths import (
    app_data_path,
    browser_profiles_path,
    config_path,
    logs_path,
    runs_path,
)


@dataclass(frozen=True)
class DiagnosticItem:
    name: str
    value: str


def collect_diagnostics() -> list[DiagnosticItem]:
    return [
        DiagnosticItem("App version", __version__),
        DiagnosticItem("PyInstaller bundle", "yes" if is_pyinstaller_bundle() else "no"),
        DiagnosticItem("App data directory", str(app_data_path())),
        DiagnosticItem("Config directory", str(config_path())),
        DiagnosticItem("Logs directory", str(logs_path())),
        DiagnosticItem("Runs directory", str(runs_path())),
        DiagnosticItem("Browser profiles directory", str(browser_profiles_path())),
        DiagnosticItem("Python executable", getattr(sys, "executable", "") or "unavailable"),
        DiagnosticItem("Current working directory", str(Path.cwd())),
        DiagnosticItem("Playwright import", _availability("playwright.sync_api")),
        DiagnosticItem("PySide6 import", _availability("PySide6")),
        DiagnosticItem("Windows UI Automation dependencies", _windows_uia_status()),
    ]


def format_diagnostics(items: list[DiagnosticItem] | None = None) -> str:
    rows = items if items is not None else collect_diagnostics()
    return "\n".join(f"{item.name}: {item.value}" for item in rows)


def is_pyinstaller_bundle() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def _windows_uia_status() -> str:
    modules = ["pywinauto"]
    if os.name == "nt":
        modules.extend(["pythoncom", "pywintypes"])
    missing = [module for module in modules if not _module_available(module)]
    if missing:
        return "missing " + ", ".join(missing)
    return "available"


def _availability(module: str) -> str:
    return "available" if _module_available(module) else "missing"


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
