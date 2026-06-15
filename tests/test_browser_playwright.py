from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

from ritualist.adapters.browser_playwright import PlaywrightBrowserAdapter


class FakePage:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.visible_text: set[str] = set()

    def goto(self, url: str, *, wait_until: str) -> None:
        self.urls.append(url)

    def get_by_text(self, text: str, *, exact: bool):
        return FakeTextLocator(text in self.visible_text)


class FakeTextLocator:
    def __init__(self, visible: bool) -> None:
        self.visible = visible

    @property
    def first(self):
        return self

    def wait_for(self, *, state: str, timeout: float) -> None:
        if not self.visible:
            raise FakePlaywrightTimeout("not visible")


class FakeContext:
    def __init__(self) -> None:
        self.pages: list[FakePage] = []
        self.closed = False

    def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.context = FakeContext()
        self.calls: list[tuple[str, dict[str, object]]] = []

    def launch_persistent_context(self, *, user_data_dir: str, **options):
        self.calls.append((user_data_dir, options))
        return self.context


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakePlaywrightTimeout(Exception):
    pass


def install_fake_playwright(monkeypatch, fake_playwright: FakePlaywright) -> None:
    playwright = ModuleType("playwright")
    playwright.__path__ = []
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: SimpleNamespace(start=lambda: fake_playwright)
    sync_api.TimeoutError = FakePlaywrightTimeout
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_browser_open_uses_persistent_profile_and_new_window(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)

    adapter = PlaywrightBrowserAdapter()
    adapter.open_url("https://example.test/one", profile="gaming", new_window=False)
    adapter.open_url("https://example.test/two", profile="gaming", new_window=True, keep_open=True)

    user_data_dir, options = fake_playwright.chromium.calls[0]
    assert Path(user_data_dir) == tmp_path / "chromium" / "gaming"
    assert options["headless"] is False
    assert len(fake_playwright.chromium.context.pages) == 2
    assert fake_playwright.chromium.context.pages[0].urls == ["https://example.test/one"]
    assert fake_playwright.chromium.context.pages[1].urls == ["https://example.test/two"]
    assert adapter._keep_open_requested is True


def test_browser_text_visible_is_read_only(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)
    adapter = PlaywrightBrowserAdapter()
    adapter.open_url("https://example.test/one", profile="gaming")
    page = fake_playwright.chromium.context.pages[0]
    page.visible_text.add("Connected")

    assert adapter.text_visible(text="Connected", exact=True, timeout_seconds=0.01) is True
    assert adapter.text_visible(text="Missing", exact=True, timeout_seconds=0.01) is False
    assert page.urls == ["https://example.test/one"]
