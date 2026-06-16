from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ritualist.actions.base import AdapterBundle
from ritualist.overlay import ScreenRect, TargetRegion


@dataclass
class RecordingAdapter:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    failures: dict[str, Exception] = field(default_factory=dict)
    responses: dict[str, Any] = field(default_factory=dict)

    def record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))
        if name in self.failures:
            raise self.failures[name]

    def response(self, name: str, default: Any) -> Any:
        value = self.responses.get(name, default)
        if isinstance(value, list):
            if len(value) > 1:
                return value.pop(0)
            if value:
                return value[0]
            return default
        return value


class FakeShellAdapter(RecordingAdapter):
    def launch(self, **kwargs: Any) -> None:
        self.record("launch", **kwargs)

    def wait_process(self, process_name: str, *, timeout_seconds: float) -> None:
        self.record("wait_process", process_name, timeout_seconds=timeout_seconds)

    def process_running(self, process_name: str, *, timeout_seconds: float = 0) -> bool:
        self.record("process_running", process_name, timeout_seconds=timeout_seconds)
        return bool(self.response("process_running", True))


class FakeBrowserAdapter(RecordingAdapter):
    def open_url(
        self,
        url: str,
        *,
        browser: str = "chromium",
        profile: str = "default",
        new_window: bool = False,
        keep_open: bool = False,
    ) -> None:
        self.record(
            "open_url",
            url,
            browser=browser,
            profile=profile,
            new_window=new_window,
            keep_open=keep_open,
        )

    def configure_media(self, **kwargs: Any) -> None:
        self.record("configure_media", **kwargs)

    def text_visible(self, **kwargs: Any) -> bool:
        self.record("text_visible", **kwargs)
        return bool(self.response("text_visible", True))


class FakeWindowAdapter(RecordingAdapter):
    def window_exists(self, **kwargs: Any) -> bool:
        self.record("window_exists", **kwargs)
        return bool(self.response("window_exists", True))

    def find_window_region(self, **kwargs: Any) -> TargetRegion:
        self.record("find_window_region", **kwargs)
        return self.response("find_window_region", _fake_window_region(kwargs))

    def focus(self, **kwargs: Any) -> TargetRegion:
        self.record("focus", **kwargs)
        return self.response("focus", _fake_window_region(kwargs))

    def minimize(self, **kwargs: Any) -> TargetRegion:
        self.record("minimize", **kwargs)
        return self.response("minimize", _fake_window_region(kwargs))

    def move_window(self, **kwargs: Any) -> TargetRegion:
        self.record("move_window", **kwargs)
        return self.response("move_window", _fake_layout_region(kwargs))

    def resize_window(self, **kwargs: Any) -> TargetRegion:
        self.record("resize_window", **kwargs)
        return self.response("resize_window", _fake_layout_region(kwargs))

    def maximize(self, **kwargs: Any) -> TargetRegion:
        self.record("maximize", **kwargs)
        return self.response("maximize", _fake_window_region(kwargs))

    def maximize_window(self, **kwargs: Any) -> TargetRegion:
        self.record("maximize_window", **kwargs)
        return self.response("maximize_window", _fake_window_region(kwargs))

    def restore_window(self, **kwargs: Any) -> TargetRegion:
        self.record("restore_window", **kwargs)
        return self.response("restore_window", _fake_window_region(kwargs))

    def snap_left(self, **kwargs: Any) -> TargetRegion:
        self.record("snap_left", **kwargs)
        return self.response("snap_left", _fake_snap_region(kwargs, "left"))

    def snap_right(self, **kwargs: Any) -> TargetRegion:
        self.record("snap_right", **kwargs)
        return self.response("snap_right", _fake_snap_region(kwargs, "right"))

    def snap_top(self, **kwargs: Any) -> TargetRegion:
        self.record("snap_top", **kwargs)
        return self.response("snap_top", _fake_snap_region(kwargs, "top"))

    def snap_bottom(self, **kwargs: Any) -> TargetRegion:
        self.record("snap_bottom", **kwargs)
        return self.response("snap_bottom", _fake_snap_region(kwargs, "bottom"))

    def list_monitors(self) -> list[ScreenRect]:
        self.record("list_monitors")
        default = [ScreenRect(0, 0, 1920, 1080)]
        value = self.responses.get("list_monitors", default)
        if isinstance(value, list):
            if not value:
                return default
            if all(isinstance(item, ScreenRect) for item in value):
                return value
            if len(value) > 1:
                return value.pop(0)
            return value[0]
        return value

    def wait(self, **kwargs: Any) -> TargetRegion:
        self.record("wait", **kwargs)
        return self.response("wait", _fake_window_region(kwargs))


def _fake_window_region(kwargs: dict[str, Any]) -> TargetRegion:
    return TargetRegion(
        rect=ScreenRect(10, 20, 300, 200),
        window_title=kwargs.get("title_contains") or kwargs.get("process_name") or "Window",
    )


def _fake_layout_region(kwargs: dict[str, Any]) -> TargetRegion:
    rect = ScreenRect(
        int(kwargs.get("x", 10)),
        int(kwargs.get("y", 20)),
        int(kwargs.get("width", 300)),
        int(kwargs.get("height", 200)),
    )
    return TargetRegion(
        rect=rect,
        window_title=kwargs.get("title_contains") or kwargs.get("process_name") or "Window",
    )


def _fake_snap_region(kwargs: dict[str, Any], edge: str) -> TargetRegion:
    if edge == "left":
        rect = ScreenRect(0, 0, 960, 1080)
    elif edge == "right":
        rect = ScreenRect(960, 0, 960, 1080)
    elif edge == "top":
        rect = ScreenRect(0, 0, 1920, 540)
    else:
        rect = ScreenRect(0, 540, 1920, 540)
    title = kwargs.get("title_contains") or kwargs.get("process_name") or "Window"
    return TargetRegion(rect=rect, window_title=title)


class FakeDesktopAdapter(RecordingAdapter):
    def text_visible(self, **kwargs: Any) -> bool:
        self.record("text_visible", **kwargs)
        return bool(self.response("text_visible", True))

    def find_text_region(self, **kwargs: Any) -> TargetRegion:
        self.record("find_text_region", **kwargs)
        return self.response("find_text_region", _fake_text_region(kwargs))

    def click_text(self, **kwargs: Any) -> TargetRegion:
        self.record("click_text", **kwargs)
        return self.response("click_text", _fake_text_region(kwargs))


def _fake_text_region(kwargs: dict[str, Any]) -> TargetRegion:
    return TargetRegion(
        rect=ScreenRect(30, 40, 120, 36),
        window_title=kwargs.get("window_title_contains"),
        target_text=kwargs.get("text"),
        control_type=kwargs.get("control_type"),
    )


class FakeInputAdapter(RecordingAdapter):
    def hotkey(self, keys: list[str]) -> None:
        self.record("hotkey", keys)


@dataclass
class FakeAdapters:
    shell: FakeShellAdapter = field(default_factory=FakeShellAdapter)
    browser: FakeBrowserAdapter = field(default_factory=FakeBrowserAdapter)
    window: FakeWindowAdapter = field(default_factory=FakeWindowAdapter)
    desktop: FakeDesktopAdapter = field(default_factory=FakeDesktopAdapter)
    input: FakeInputAdapter = field(default_factory=FakeInputAdapter)

    def bundle(self) -> AdapterBundle:
        return AdapterBundle(
            shell=self.shell,
            browser=self.browser,
            window=self.window,
            desktop=self.desktop,
            input=self.input,
        )
