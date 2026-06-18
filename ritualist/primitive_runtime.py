from __future__ import annotations

import hashlib
import json
import platform
import socket
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions.base import AdapterBundle
from .diagnostics import collect_diagnostics
from .errors import DependencyMissingError, PlatformUnsupportedError, RitualistError
from .paths import logs_dir
from .primitives import (
    PrimitiveArtifact,
    PrimitiveExecutionResult,
    PrimitivePlanStep,
    PrimitiveRegistry,
    PrimitiveRisk,
    PrimitiveVerification,
    create_primitive_registry,
)


FORBIDDEN_DIAGNOSTIC_CLASSES: tuple[str, ...] = (
    "cookies",
    "browser_history",
    "passwords",
    "tokens",
    "private_keys",
    "screenshots",
    "clipboard_contents",
)


def run_read_only_primitive(
    primitive_id: str,
    *,
    parameters: dict[str, Any] | None = None,
    dry_run: bool = False,
    adapters: AdapterBundle | None = None,
    registry: PrimitiveRegistry | None = None,
) -> PrimitiveExecutionResult:
    resolved_registry = registry or create_primitive_registry()
    try:
        spec = resolved_registry.spec(primitive_id)
    except KeyError as exc:
        raise RitualistError(str(exc)) from exc
    if spec.risk is not PrimitiveRisk.READ_ONLY:
        raise RitualistError(
            f"primitive run only supports read-only primitives; {primitive_id} is {spec.risk.value}"
        )

    plan_step = PrimitivePlanStep(
        primitive_id=primitive_id,
        action_name=spec.action_name,
        parameters=dict(parameters or {}),
        risk=spec.risk,
    )
    if dry_run:
        return PrimitiveExecutionResult(
            status="dry-run",
            message=f"would run read-only primitive {primitive_id}",
            verification=PrimitiveVerification(
                name=primitive_id,
                status="dry-run",
                message="no host state was read",
            ),
            details={"primitive_id": primitive_id, "parameters": _redact_parameters(plan_step.parameters)},
        )

    family, _, verb = primitive_id.rpartition(".")
    if family == "app.process":
        return _process_primitive(verb, plan_step.parameters)
    if family == "window.topology":
        return _window_primitive(verb, plan_step.parameters, adapters=adapters)
    if family == "uia.element":
        return _uia_primitive(verb, plan_step.parameters, adapters=adapters)
    if family == "browser.assert":
        return _browser_assert_primitive(verb, plan_step.parameters, adapters=adapters)
    if family == "runtime.assert":
        return _runtime_assert_primitive(verb, plan_step.parameters)
    if family == "hardware.inventory":
        return _hardware_primitive(verb, plan_step.parameters)
    if family == "network.connectivity":
        return _network_primitive(verb, plan_step.parameters)
    if family == "diagnostics.bundle":
        return _diagnostics_primitive(verb, plan_step.parameters)
    raise RitualistError(f"no read-only primitive executor for {primitive_id}")


def _process_primitive(verb: str, parameters: dict[str, Any]) -> PrimitiveExecutionResult:
    psutil = _psutil()
    if verb == "list":
        processes = _process_rows(psutil)
        return _success("listed processes", {"processes": processes, "count": len(processes)})
    if verb == "find":
        rows = _find_processes(psutil, parameters)
        return _success("found matching processes", {"processes": rows, "count": len(rows)})
    if verb == "is_running":
        _require_process_filter(parameters)
        matched = bool(_find_processes(psutil, parameters))
        return _success("process running check completed", {"matched": matched})
    if verb in {"wait_running", "wait_exit"}:
        _require_process_filter(parameters)
        timeout = _float_parameter(parameters, "timeout_seconds", 30.0)
        deadline = time.monotonic() + timeout
        while True:
            running = bool(_find_processes(psutil, parameters))
            if (verb == "wait_running" and running) or (verb == "wait_exit" and not running):
                return _success(
                    "process wait completed",
                    {"matched": True, "waited_for": verb, "timeout_seconds": timeout},
                )
            if time.monotonic() >= deadline:
                return _failed(
                    "process wait timed out",
                    {"matched": False, "waited_for": verb, "timeout_seconds": timeout},
                )
            time.sleep(0.25)
    raise RitualistError(f"unsupported app.process primitive verb: {verb}")


def _window_primitive(
    verb: str,
    parameters: dict[str, Any],
    *,
    adapters: AdapterBundle | None,
) -> PrimitiveExecutionResult:
    if verb == "get_foreground":
        manager = _window_adapter(adapters)
        return _success(
            "foreground window read",
            {"title": manager.foreground_window_title()},
        )
    if verb == "monitor_list":
        manager = _window_adapter(adapters)
        monitors = [_screen_rect_to_dict(rect) for rect in manager.list_monitors()]
        return _success("monitors listed", {"monitors": monitors, "count": len(monitors)})

    title_contains = _optional_text(parameters, "title_contains")
    process_name = _optional_text(parameters, "process_name")
    if verb == "list_windows":
        windows = _list_windows(title_contains=title_contains, process_name=process_name, adapters=adapters)
        return _success("windows listed", {"windows": windows, "count": len(windows)})
    if verb in {"find_window", "get_bounds"}:
        windows = _list_windows(title_contains=title_contains, process_name=process_name, adapters=adapters)
        if not windows:
            return _failed("window not found", {"matched": False, "windows": []})
        first = windows[0]
        return _success("window found", {"matched": True, "window": first, "bounds": first.get("bounds")})
    raise RitualistError(f"unsupported window.topology primitive verb: {verb}")


def _uia_primitive(
    verb: str,
    parameters: dict[str, Any],
    *,
    adapters: AdapterBundle | None,
) -> PrimitiveExecutionResult:
    desktop = _desktop_adapter(adapters)
    title = _required_text(parameters, "window_title_contains")
    control_type = _optional_text(parameters, "control_type")
    limit = _int_parameter(parameters, "limit", 100)
    if verb in {"list_labels", "candidate_dump"}:
        inspections = desktop.inspect_windows(
            title_contains=title,
            limit=limit,
            control_type=control_type,
        )
        windows = [
            {"title": inspection.title, "labels": list(inspection.labels)}
            for inspection in inspections
        ]
        return _success(
            "visible labels listed",
            {"windows": windows, "count": len(windows), "primitive": f"uia.element.{verb}"},
        )
    if verb in {"find_text", "find_control"}:
        text = _required_text(parameters, "text")
        exact = _bool_parameter(parameters, "exact", True)
        region = desktop.find_text_region(
            text=text,
            window_title_contains=title,
            control_type=control_type,
            exact=exact,
            timeout_seconds=float(parameters.get("timeout_seconds") or 0),
        )
        return _success(
            "UI Automation text searched",
            {
                "matched": bool(region and region.rect),
                "target": text,
                "region": _target_region_to_dict(region),
            },
        )
    raise RitualistError(f"unsupported uia.element primitive verb: {verb}")


def _browser_assert_primitive(
    verb: str,
    parameters: dict[str, Any],
    *,
    adapters: AdapterBundle | None,
) -> PrimitiveExecutionResult:
    browser = _browser_adapter(adapters)
    timeout = _float_parameter(parameters, "timeout_seconds", 0.0)
    if verb == "text_visible":
        matched = browser.text_visible(
            text=_required_text(parameters, "text"),
            exact=_bool_parameter(parameters, "exact", True),
            timeout_seconds=timeout,
        )
    elif verb == "title_matches":
        matched = browser.title_matches(
            title=_optional_text(parameters, "title"),
            title_contains=_optional_text(parameters, "title_contains"),
            timeout_seconds=timeout,
        )
    elif verb == "url_matches":
        matched = browser.url_matches(
            url=_optional_text(parameters, "url"),
            url_contains=_optional_text(parameters, "url_contains"),
            timeout_seconds=timeout,
        )
    elif verb == "element_visible":
        matched = browser.element_visible(
            text=_optional_text(parameters, "text"),
            role=_optional_text(parameters, "role"),
            accessible_name=_optional_text(parameters, "accessible_name"),
            test_id=_optional_text(parameters, "test_id"),
            exact=_bool_parameter(parameters, "exact", True),
            timeout_seconds=timeout,
        )
    else:
        raise RitualistError(f"unsupported browser.assert primitive verb: {verb}")
    return _success("browser assertion evaluated", {"matched": bool(matched)})


def _runtime_assert_primitive(verb: str, parameters: dict[str, Any]) -> PrimitiveExecutionResult:
    if verb == "value_equals":
        matched = parameters.get("left") == parameters.get("right")
        return _success(
            "runtime value comparison evaluated",
            {"matched": matched},
        )
    raise RitualistError(f"unsupported runtime.assert primitive verb: {verb}")


def _hardware_primitive(verb: str, parameters: dict[str, Any]) -> PrimitiveExecutionResult:
    _ensure_windows("hardware inventory primitives")
    psutil = _optional_psutil()
    data = {
        "bios": _bios_summary(),
        "cpu": _cpu_summary(psutil),
        "gpu": _unavailable_inventory("GPU inventory"),
        "motherboard": _unavailable_inventory("motherboard inventory"),
        "disks": _disk_summary(psutil),
        "network_adapters": _network_adapter_summary(psutil),
        "pnp_devices": _unavailable_inventory("PnP inventory"),
    }
    if verb == "snapshot":
        return _success("hardware snapshot collected", data)
    if verb in data:
        return _success(f"hardware {verb} collected", {verb: data[verb]})
    raise RitualistError(f"unsupported hardware.inventory primitive verb: {verb}")


def _network_primitive(verb: str, parameters: dict[str, Any]) -> PrimitiveExecutionResult:
    if verb == "profile":
        return _success("network profile read", _network_profile())
    if verb == "dns":
        return _success("DNS probe completed", _dns_probe(_required_text(parameters, "host")))
    if verb == "tcp":
        return _success(
            "TCP probe completed",
            _tcp_probe(
                _required_text(parameters, "host"),
                _int_parameter(parameters, "port"),
                timeout_seconds=_float_parameter(parameters, "timeout_seconds", 3.0),
            ),
        )
    if verb == "route_hint":
        return _success(
            "route hint collected",
            _route_hint(
                _required_text(parameters, "host"),
                _int_parameter(parameters, "port", 443),
            ),
        )
    if verb == "snapshot":
        host = str(parameters.get("host") or "example.com")
        return _success(
            "network snapshot collected",
            {
                "profile": _network_profile(),
                "dns": _dns_probe(host),
                "route_hint": _route_hint(host, 443),
            },
        )
    raise RitualistError(f"unsupported network.connectivity primitive verb: {verb}")


def _diagnostics_primitive(verb: str, parameters: dict[str, Any]) -> PrimitiveExecutionResult:
    preset = {
        "collect_minimal": "minimal",
        "collect_support": "support",
        "collect_gamer_crash": "gamer_crash",
    }.get(verb)
    if preset is None:
        raise RitualistError(f"unsupported diagnostics.bundle primitive verb: {verb}")
    output_root = Path(parameters["output_dir"]) if parameters.get("output_dir") else logs_dir() / "diagnostics"
    bundle_dir = output_root / f"{_timestamp()}_{preset}"
    bundle_dir.mkdir(parents=True, exist_ok=False)

    diagnostics_payload = {
        "schema_version": "diagnostics.bundle.v1",
        "preset": preset,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "items": [{"name": item.name, "value": item.value} for item in collect_diagnostics()],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    if preset in {"support", "gamer_crash"}:
        diagnostics_payload["notes"] = [
            "Recent run logs are not copied by default.",
            "Screenshots, browser history, cookies, clipboard contents, passwords, tokens, and private keys are excluded.",
        ]
    redaction_summary = {
        "forbidden_classes_excluded": list(FORBIDDEN_DIAGNOSTIC_CLASSES),
        "screenshots_included": False,
        "clipboard_included": False,
        "browser_history_included": False,
        "cookies_included": False,
    }
    _write_json(bundle_dir / "diagnostics.json", diagnostics_payload)
    _write_json(bundle_dir / "redaction_summary.json", redaction_summary)
    (bundle_dir / "summary.txt").write_text(
        "\n".join(f"{item.name}: {item.value}" for item in collect_diagnostics()),
        encoding="utf-8",
    )
    manifest = _artifact_manifest(bundle_dir)
    _write_json(bundle_dir / "manifest.json", manifest)
    archive_path = _zip_bundle(bundle_dir)
    manifest = _artifact_manifest(bundle_dir)
    _write_json(bundle_dir / "manifest.json", manifest)
    artifacts = tuple(
        PrimitiveArtifact(
            artifact_type="zip" if path == archive_path else path.suffix.lstrip(".") or "file",
            name=path.name,
            path=str(path),
            redacted=True,
            details={"sha256": _sha256(path)} if path.is_file() else {},
        )
        for path in sorted([*bundle_dir.iterdir(), archive_path], key=lambda item: str(item))
        if path.is_file()
    )
    return PrimitiveExecutionResult(
        status="success",
        message=f"collected {preset} diagnostics bundle",
        verification=PrimitiveVerification(
            name=f"diagnostics.bundle.{verb}",
            status="success",
            message="forbidden secret classes excluded",
            details=redaction_summary,
        ),
        artifacts=artifacts,
        details={
            "preset": preset,
            "bundle_dir": str(bundle_dir),
            "archive": str(archive_path),
            "redaction_summary": redaction_summary,
        },
    )


def _success(message: str, details: dict[str, Any]) -> PrimitiveExecutionResult:
    return PrimitiveExecutionResult(
        status="success",
        message=message,
        verification=PrimitiveVerification(name="read_only", status="success", message=message),
        details=details,
    )


def _failed(message: str, details: dict[str, Any]) -> PrimitiveExecutionResult:
    return PrimitiveExecutionResult(
        status="failed",
        message=message,
        verification=PrimitiveVerification(name="read_only", status="failed", message=message),
        details=details,
    )


def _psutil() -> Any:
    try:
        import psutil
    except ImportError as exc:
        raise DependencyMissingError(
            "process inventory requires optional dependency psutil; install ritualist[windows]"
        ) from exc
    return psutil


def _optional_psutil() -> Any | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil


def _process_rows(psutil: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "status"]):
        try:
            rows.append(
                {
                    "pid": int(process.info["pid"]),
                    "name": str(process.info.get("name") or ""),
                    "status": str(process.info.get("status") or "unknown"),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(rows, key=lambda row: (str(row["name"]).casefold(), int(row["pid"])))


def _find_processes(psutil: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    pid = _optional_int_parameter(parameters, "pid")
    name = _optional_text(parameters, "name") or _optional_text(parameters, "process_name")
    contains = _optional_text(parameters, "contains")
    rows = _process_rows(psutil)
    if pid is not None:
        return [row for row in rows if int(row["pid"]) == pid]
    if name:
        normalized = name.casefold()
        return [row for row in rows if str(row["name"]).casefold() == normalized]
    if contains:
        normalized = contains.casefold()
        return [row for row in rows if normalized in str(row["name"]).casefold()]
    return rows


def _require_process_filter(parameters: dict[str, Any]) -> None:
    if (
        parameters.get("pid") is None
        and not _optional_text(parameters, "name")
        and not _optional_text(parameters, "process_name")
        and not _optional_text(parameters, "contains")
    ):
        raise RitualistError(
            "process primitive requires one of pid, name, process_name, or contains"
        )


def _window_adapter(adapters: AdapterBundle | None) -> Any:
    if adapters is not None:
        return adapters.window
    from .adapters.window_manager import WindowsWindowManager

    return WindowsWindowManager()


def _desktop_adapter(adapters: AdapterBundle | None) -> Any:
    if adapters is not None:
        return adapters.desktop
    from .adapters.windows_uia import WindowsUIAutomationAdapter

    return WindowsUIAutomationAdapter()


def _browser_adapter(adapters: AdapterBundle | None) -> Any:
    if adapters is not None:
        return adapters.browser
    from .adapters.browser_playwright import PlaywrightBrowserAdapter

    return PlaywrightBrowserAdapter()


def _list_windows(
    *,
    title_contains: str | None,
    process_name: str | None,
    adapters: AdapterBundle | None,
) -> list[dict[str, Any]]:
    manager = _window_adapter(adapters)
    if hasattr(manager, "list_windows"):
        return list(manager.list_windows(title_contains=title_contains, process_name=process_name))
    region = manager.find_window_region(
        title_contains=title_contains,
        process_name=process_name,
        timeout_seconds=0,
    )
    return [_target_region_to_window(region)]


def _target_region_to_window(region: Any) -> dict[str, Any]:
    return {
        "title": getattr(region, "window_title", "") or "",
        "bounds": _screen_rect_to_dict(getattr(region, "rect", None)),
    }


def _target_region_to_dict(region: Any) -> dict[str, Any] | None:
    if region is None:
        return None
    return {
        "bounds": _screen_rect_to_dict(getattr(region, "rect", None)),
        "window_title": getattr(region, "window_title", None),
        "target_text": getattr(region, "target_text", None),
        "control_type": getattr(region, "control_type", None),
    }


def _screen_rect_to_dict(rect: Any) -> dict[str, int] | None:
    if rect is None:
        return None
    return {
        "x": int(rect.x),
        "y": int(rect.y),
        "width": int(rect.width),
        "height": int(rect.height),
    }


def _ensure_windows(feature: str) -> None:
    if sys.platform != "win32":
        raise PlatformUnsupportedError(f"{feature} are only supported on Windows")


def _bios_summary() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
    }


def _cpu_summary(psutil: Any | None) -> dict[str, Any]:
    data = {
        "processor": platform.processor() or platform.machine(),
        "logical_count": psutil.cpu_count(logical=True) if psutil is not None else None,
        "physical_count": psutil.cpu_count(logical=False) if psutil is not None else None,
    }
    return {key: value for key, value in data.items() if value is not None}


def _disk_summary(psutil: Any | None) -> list[dict[str, Any]]:
    if psutil is None:
        return []
    rows: list[dict[str, Any]] = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue
        rows.append(
            {
                "device": partition.device,
                "fstype": partition.fstype,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
            }
        )
    return rows


def _network_adapter_summary(psutil: Any | None) -> list[dict[str, Any]]:
    if psutil is None:
        return []
    rows: list[dict[str, Any]] = []
    for name, addresses in psutil.net_if_addrs().items():
        families = sorted({str(address.family).rsplit(".", 1)[-1] for address in addresses})
        rows.append({"name": name, "address_families": families})
    return rows


def _unavailable_inventory(name: str) -> dict[str, str]:
    return {
        "status": "unavailable",
        "reason": f"{name} is not collected without additional read-only inventory providers",
    }


def _network_profile() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "fqdn_available": bool(socket.getfqdn()),
        "platform": platform.system(),
    }


def _dns_probe(host: str) -> dict[str, Any]:
    try:
        results = socket.getaddrinfo(host, None)
    except OSError as exc:
        return {"host": host, "resolved": False, "error": str(exc)}
    families = sorted({str(result[0]).rsplit(".", 1)[-1] for result in results})
    return {"host": host, "resolved": True, "address_count": len(results), "families": families}


def _tcp_probe(host: str, port: int, *, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            elapsed_ms = (time.monotonic() - started) * 1000
            return {"host": host, "port": int(port), "connected": True, "elapsed_ms": round(elapsed_ms, 3)}
    except OSError as exc:
        elapsed_ms = (time.monotonic() - started) * 1000
        return {
            "host": host,
            "port": int(port),
            "connected": False,
            "elapsed_ms": round(elapsed_ms, 3),
            "error": str(exc),
        }


def _route_hint(host: str, port: int) -> dict[str, Any]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, int(port)))
            local_address = sock.getsockname()[0]
    except OSError as exc:
        return {"host": host, "port": int(port), "available": False, "error": str(exc)}
    return {"host": host, "port": int(port), "available": True, "local_address": local_address}


def _artifact_manifest(bundle_dir: Path) -> dict[str, Any]:
    files = [
        {
            "name": path.name,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(bundle_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    ]
    return {
        "schema_version": "diagnostics.artifacts.v1",
        "files": files,
        "redacted": True,
        "forbidden_classes_excluded": list(FORBIDDEN_DIAGNOSTIC_CLASSES),
    }


def _zip_bundle(bundle_dir: Path) -> Path:
    archive_path = bundle_dir.with_suffix(".zip")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    return archive_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _redact_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in parameters.items():
        if any(marker in key.casefold() for marker in ("password", "secret", "token", "key")):
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted


def _required_text(parameters: dict[str, Any], name: str) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RitualistError(f"primitive parameter '{name}' is required")
    return value.strip()


def _optional_text(parameters: dict[str, Any], name: str) -> str | None:
    value = parameters.get(name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_parameter(parameters: dict[str, Any], name: str, default: bool) -> bool:
    value = parameters.get(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise RitualistError(f"primitive parameter '{name}' must be a boolean")


def _float_parameter(parameters: dict[str, Any], name: str, default: float) -> float:
    value = parameters.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RitualistError(f"primitive parameter '{name}' must be a number") from exc


def _optional_int_parameter(parameters: dict[str, Any], name: str) -> int | None:
    value = parameters.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RitualistError(f"primitive parameter '{name}' must be an integer") from exc


def _int_parameter(parameters: dict[str, Any], name: str, default: int | None = None) -> int:
    value = parameters.get(name)
    if value is None:
        if default is not None:
            return default
        raise RitualistError(f"primitive parameter '{name}' is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RitualistError(f"primitive parameter '{name}' must be an integer") from exc
