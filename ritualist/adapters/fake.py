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


class FakeShellAdapter(RecordingAdapter):
    def launch(self, **kwargs: Any) -> None:
        self.record("launch", **kwargs)

    def wait_process(self, process_name: str, *, timeout_seconds: float) -> None:
        self.record("wait_process", process_name, timeout_seconds=timeout_seconds)

    def process_running(self, process_name: str, *, timeout_seconds: float = 0) -> bool:
        self.record("process_running", process_name, timeout_seconds=timeout_seconds)
        return bool(self.responses.get("process_running", True))


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
        return bool(self.responses.get("text_visible", True))


class FakeWindowAdapter(RecordingAdapter):
    def window_exists(self, **kwargs: Any) -> bool:
        self.record("window_exists", **kwargs)
        return bool(self.responses.get("window_exists", True))

    def find_window_region(self, **kwargs: Any) -> TargetRegion:
        self.record("find_window_region", **kwargs)
        return TargetRegion(
            rect=ScreenRect(10, 20, 300, 200),
            window_title=kwargs.get("title_contains") or kwargs.get("process_name") or "Window",
        )

    def focus(self, **kwargs: Any) -> None:
        self.record("focus", **kwargs)

    def minimize(self, **kwargs: Any) -> None:
        self.record("minimize", **kwargs)

    def maximize(self, **kwargs: Any) -> None:
        self.record("maximize", **kwargs)

    def wait(self, **kwargs: Any) -> None:
        self.record("wait", **kwargs)


class FakeDesktopAdapter(RecordingAdapter):
    def text_visible(self, **kwargs: Any) -> bool:
        self.record("text_visible", **kwargs)
        return bool(self.responses.get("text_visible", True))

    def find_text_region(self, **kwargs: Any) -> TargetRegion:
        self.record("find_text_region", **kwargs)
        return TargetRegion(
            rect=ScreenRect(30, 40, 120, 36),
            window_title=kwargs.get("window_title_contains"),
            target_text=kwargs.get("text"),
            control_type=kwargs.get("control_type"),
        )

    def click_text(self, **kwargs: Any) -> None:
        self.record("click_text", **kwargs)


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
