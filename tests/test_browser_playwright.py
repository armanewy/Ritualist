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
        self.visible_roles: set[tuple[str, str]] = set()
        self.visible_test_ids: set[str] = set()
        self.clicked: list[tuple[str, str]] = []
        self._title = "Example Page"
        self.url = "about:blank"

    def goto(self, url: str, *, wait_until: str) -> None:
        self.urls.append(url)
        self.url = url

    def title(self) -> str:
        return self._title

    def get_by_text(self, text: str, *, exact: bool):
        return FakeTextLocator(("text", text), text in self.visible_text, self.clicked)

    def get_by_role(self, role: str, *, name: str, exact: bool):
        return FakeTextLocator(("role", f"{role}:{name}"), (role, name) in self.visible_roles, self.clicked)

    def get_by_test_id(self, test_id: str):
        return FakeTextLocator(("test_id", test_id), test_id in self.visible_test_ids, self.clicked)


class FakeTextLocator:
    def __init__(self, target: tuple[str, str], visible: bool, clicked: list[tuple[str, str]]) -> None:
        self.target = target
        self.visible = visible
        self.clicked = clicked

    @property
    def first(self):
        return self

    def wait_for(self, *, state: str, timeout: float) -> None:
        if not self.visible:
            raise FakePlaywrightTimeout("not visible")

    def click(self, *, timeout: float) -> None:
        if not self.visible:
            raise FakePlaywrightTimeout("not visible")
        self.clicked.append(self.target)


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


def test_browser_open_clean_start_adds_prevention_launch_flags(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)

    adapter = PlaywrightBrowserAdapter()
    adapter.open_url("https://example.test/one", profile="gaming", clean_start=True)

    _user_data_dir, options = fake_playwright.chromium.calls[0]
    assert "--no-first-run" in options["args"]
    assert "--no-default-browser-check" in options["args"]
    assert "--disable-session-crashed-bubble" in options["args"]
    assert "--hide-crash-restore-bubble" in options["args"]


def test_browser_open_rejects_non_dedicated_profiles(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)

    adapter = PlaywrightBrowserAdapter()

    try:
        adapter.open_url(
            "https://example.test/one",
            profile="gaming",
            use_dedicated_profile=False,
        )
    except Exception as exc:
        assert "managed browser profiles" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("non-dedicated browser profiles should be rejected")

    assert fake_playwright.chromium.calls == []


def test_browser_open_restore_prompt_absent_noops(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)

    adapter = PlaywrightBrowserAdapter()
    adapter.open_url(
        "https://example.test/one",
        profile="gaming",
        dismiss_restore_prompt=True,
    )

    page = fake_playwright.chromium.context.pages[0]
    assert page.clicked == []
    assert page.urls == ["https://example.test/one"]


def test_browser_open_unknown_prompt_is_not_dismissed(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    page = FakePage()
    page.visible_text.add("Update Chrome?")
    page.visible_roles.add(("button", "OK"))
    fake_playwright.chromium.context.pages.append(page)
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)

    adapter = PlaywrightBrowserAdapter()
    adapter.open_url(
        "https://example.test/one",
        profile="gaming",
        dismiss_restore_prompt=True,
    )

    assert page.clicked == []
    assert page.urls == ["https://example.test/one"]


def test_browser_open_known_restore_prompt_dismisses_known_button(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    page = FakePage()
    page.visible_text.add("Restore pages?")
    page.visible_roles.add(("button", "Cancel"))
    fake_playwright.chromium.context.pages.append(page)
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)

    adapter = PlaywrightBrowserAdapter()
    adapter.open_url(
        "https://example.test/one",
        profile="gaming",
        dismiss_restore_prompt=True,
    )

    assert page.clicked == [("role", "button:Cancel")]
    assert page.urls == ["https://example.test/one"]


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


def test_browser_structured_waits_and_clicks_use_playwright_locators(tmp_path, monkeypatch):
    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        "ritualist.adapters.browser_playwright.browser_profiles_dir",
        lambda: tmp_path,
    )
    install_fake_playwright(monkeypatch, fake_playwright)
    adapter = PlaywrightBrowserAdapter()
    adapter.open_url("https://example.test/ready", profile="gaming")
    page = fake_playwright.chromium.context.pages[0]
    page.visible_text.add("Continue")
    page.visible_roles.add(("button", "Save"))
    page.visible_test_ids.add("ready-button")

    assert adapter.title_matches(title="Example Page", title_contains=None, timeout_seconds=0) is True
    assert adapter.url_matches(url=None, url_contains="/ready", timeout_seconds=0) is True
    assert adapter.element_visible(
        text=None,
        role="button",
        accessible_name="Save",
        test_id=None,
        exact=True,
        timeout_seconds=0.01,
    ) is True

    adapter.click_text(text="Continue", exact=True, timeout_seconds=0.01)
    adapter.click_role(role="button", accessible_name="Save", exact=True, timeout_seconds=0.01)
    adapter.click_test_id(test_id="ready-button", timeout_seconds=0.01)

    assert page.clicked == [
        ("text", "Continue"),
        ("role", "button:Save"),
        ("test_id", "ready-button"),
    ]
