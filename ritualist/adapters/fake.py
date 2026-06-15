from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ritualist.actions.base import AdapterBundle


@dataclass
class RecordingAdapter:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    failures: dict[str, Exception] = field(default_factory=dict)

    def record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))
        if name in self.failures:
            raise self.failures[name]


class FakeShellAdapter(RecordingAdapter):
    def launch(self, **kwargs: Any) -> None:
        self.record("launch", **kwargs)

    def wait_process(self, process_name: str, *, timeout_seconds: float) -> None:
        self.record("wait_process", process_name, timeout_seconds=timeout_seconds)


class FakeBrowserAdapter(RecordingAdapter):
    def open_url(self, url: str, *, browser: str = "chromium") -> None:
        self.record("open_url", url, browser=browser)

    def configure_media(self, **kwargs: Any) -> None:
        self.record("configure_media", **kwargs)


class FakeWindowAdapter(RecordingAdapter):
    def focus(self, **kwargs: Any) -> None:
        self.record("focus", **kwargs)

    def minimize(self, **kwargs: Any) -> None:
        self.record("minimize", **kwargs)

    def maximize(self, **kwargs: Any) -> None:
        self.record("maximize", **kwargs)

    def wait(self, **kwargs: Any) -> None:
        self.record("wait", **kwargs)


class FakeDesktopAdapter(RecordingAdapter):
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
