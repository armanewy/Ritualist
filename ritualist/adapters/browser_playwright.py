from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ritualist.errors import DependencyMissingError, RitualistError
from ritualist.models import SAFE_ID_PATTERN
from ritualist.paths import browser_profiles_dir


class PlaywrightBrowserAdapter:
    def __init__(self) -> None:
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._browser_name: str | None = None
        self._profile: str | None = None
        self._keep_open_requested: bool = False

    def open_url(
        self,
        url: str,
        *,
        browser: str = "chromium",
        profile: str = "default",
        new_window: bool = False,
        keep_open: bool = False,
        clean_start: bool = False,
        dismiss_restore_prompt: bool = False,
        use_dedicated_profile: bool = True,
    ) -> None:
        self._keep_open_requested = keep_open
        page = self._ensure_page(
            browser=browser,
            profile=profile,
            new_window=new_window,
            clean_start=clean_start,
            use_dedicated_profile=use_dedicated_profile,
        )
        if dismiss_restore_prompt:
            _dismiss_known_restore_prompt(page)
        page.goto(url, wait_until="domcontentloaded")

    def configure_media(
        self,
        *,
        selector: str,
        play: bool | None,
        loop: bool | None,
        muted: bool | None,
        timeout_seconds: float,
    ) -> None:
        if self._page is None:
            raise RitualistError("browser.media requires a prior browser.open step")

        locator = self._page.locator(selector).first
        locator.wait_for(state="attached", timeout=timeout_seconds * 1000)
        self._page.evaluate(
            """
            async ({ selector, play, loop, muted }) => {
              const element = document.querySelector(selector);
              if (!element) {
                throw new Error(`media element not found: ${selector}`);
              }
              if (loop !== null) element.loop = loop;
              if (muted !== null) element.muted = muted;
              if (play === true) await element.play();
              if (play === false) element.pause();
            }
            """,
            {"selector": selector, "play": play, "loop": loop, "muted": muted},
        )

    def media_playing(
        self,
        *,
        selector: str,
        sample_seconds: float,
        timeout_seconds: float,
    ) -> bool:
        if self._page is None:
            raise RitualistError("browser.wait_media_playing requires a prior browser.open step")
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except ImportError as exc:
            raise DependencyMissingError(
                "browser media checks require Playwright; install ritualist[browser] and run "
                "'python -m playwright install chromium'"
            ) from exc

        locator = self._page.locator(selector).first
        try:
            locator.wait_for(state="attached", timeout=timeout_seconds * 1000)
        except PlaywrightTimeoutError:
            return False
        return bool(
            self._page.evaluate(
                """
                async ({ selector, sampleSeconds }) => {
                  const element = document.querySelector(selector);
                  if (!element) {
                    throw new Error(`media element not found: ${selector}`);
                  }
                  if (typeof element.currentTime !== "number") {
                    throw new Error(`element is not media-like: ${selector}`);
                  }
                  if (element.readyState < 2 || element.paused || element.ended) {
                    return false;
                  }
                  const startTime = element.currentTime;
                  await new Promise((resolve) => setTimeout(resolve, sampleSeconds * 1000));
                  return (
                    element.readyState >= 2 &&
                    !element.paused &&
                    !element.ended &&
                    element.currentTime > startTime + 0.01
                  );
                }
                """,
                {"selector": selector, "sampleSeconds": sample_seconds},
            )
        )

    def text_visible(self, *, text: str, exact: bool, timeout_seconds: float) -> bool:
        if self._page is None:
            raise RitualistError("assert.browser_text_visible requires a prior browser.open step")
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except ImportError as exc:
            raise DependencyMissingError(
                "browser assertions require Playwright; install ritualist[browser] and run "
                "'python -m playwright install chromium'"
            ) from exc

        locator = self._page.get_by_text(text, exact=exact).first
        try:
            locator.wait_for(state="visible", timeout=timeout_seconds * 1000)
        except PlaywrightTimeoutError:
            return False
        return True

    def title_matches(
        self,
        *,
        title: str | None,
        title_contains: str | None,
        timeout_seconds: float,
    ) -> bool:
        if self._page is None:
            raise RitualistError("browser.wait_title requires a prior browser.open step")
        current_title = self._page.title()
        if title is not None:
            return current_title == title
        if title_contains is not None:
            return title_contains in current_title
        return False

    def url_matches(
        self,
        *,
        url: str | None,
        url_contains: str | None,
        timeout_seconds: float,
    ) -> bool:
        if self._page is None:
            raise RitualistError("browser.wait_url requires a prior browser.open step")
        current_url = self._page.url
        if url is not None:
            return current_url == url
        if url_contains is not None:
            return url_contains in current_url
        return False

    def element_visible(
        self,
        *,
        text: str | None,
        role: str | None,
        accessible_name: str | None,
        test_id: str | None,
        exact: bool,
        timeout_seconds: float,
    ) -> bool:
        if self._page is None:
            raise RitualistError("browser.element_visible requires a prior browser.open step")
        locator = self._structured_locator(
            text=text,
            role=role,
            accessible_name=accessible_name,
            test_id=test_id,
            exact=exact,
        )
        return _locator_visible(locator, timeout_seconds=timeout_seconds)

    def click_text(self, *, text: str, exact: bool, timeout_seconds: float) -> None:
        if self._page is None:
            raise RitualistError("browser.click_text requires a prior browser.open step")
        locator = self._page.get_by_text(text, exact=exact).first
        locator.wait_for(state="visible", timeout=timeout_seconds * 1000)
        locator.click(timeout=timeout_seconds * 1000)

    def click_role(
        self,
        *,
        role: str,
        accessible_name: str,
        exact: bool,
        timeout_seconds: float,
    ) -> None:
        if self._page is None:
            raise RitualistError("browser.click_role requires a prior browser.open step")
        locator = self._page.get_by_role(role, name=accessible_name, exact=exact).first
        locator.wait_for(state="visible", timeout=timeout_seconds * 1000)
        locator.click(timeout=timeout_seconds * 1000)

    def click_test_id(self, *, test_id: str, timeout_seconds: float) -> None:
        if self._page is None:
            raise RitualistError("browser.click_test_id requires a prior browser.open step")
        locator = self._page.get_by_test_id(test_id).first
        locator.wait_for(state="visible", timeout=timeout_seconds * 1000)
        locator.click(timeout=timeout_seconds * 1000)

    def page_context(self) -> dict[str, str]:
        if self._page is None:
            return {}
        title = str(self._page.title() or "")
        url = _redact_url(str(getattr(self._page, "url", "") or ""))
        return {
            key: value
            for key, value in {"title": title, "url": url}.items()
            if value
        }

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None
        self._browser_name = None
        self._profile = None

    def _ensure_page(
        self,
        *,
        browser: str,
        profile: str,
        new_window: bool,
        clean_start: bool,
        use_dedicated_profile: bool,
    ) -> Any:
        if not use_dedicated_profile:
            raise RitualistError(
                "browser.open use_dedicated_profile=false is not supported; "
                "Ritualist only opens managed browser profiles"
            )
        if not SAFE_ID_PATTERN.fullmatch(profile):
            raise RitualistError(
                "browser profile must be a safe filename-like identifier "
                "(letters, numbers, hyphen, underscore)"
            )

        if (
            self._context is not None
            and self._browser_name == browser
            and self._profile == profile
            and self._page is not None
            and not new_window
        ):
            return self._page

        if self._context is not None and (self._browser_name != browser or self._profile != profile):
            self._context.close()
            self._context = None
            self._page = None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DependencyMissingError(
                "browser actions require Playwright; install ritualist[browser] and run "
                "'python -m playwright install chromium'"
            ) from exc

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._context is None:
            launch_options: dict[str, Any] = {"headless": False}
            if clean_start:
                launch_options["args"] = [
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-session-crashed-bubble",
                    "--hide-crash-restore-bubble",
                ]
            if browser == "chrome":
                launch_options["channel"] = "chrome"
            elif browser == "msedge":
                launch_options["channel"] = "msedge"
            elif browser != "chromium":
                raise RitualistError(f"unsupported browser '{browser}'")

            profile_dir = _profile_dir(browser=browser, profile=profile)
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                **launch_options,
            )
            self._browser_name = browser
            self._profile = profile

        if new_window or not self._context.pages:
            self._page = self._context.new_page()
        else:
            self._page = self._context.pages[-1]
        return self._page

    def _structured_locator(
        self,
        *,
        text: str | None,
        role: str | None,
        accessible_name: str | None,
        test_id: str | None,
        exact: bool,
    ) -> Any:
        if self._page is None:
            raise RitualistError("browser action requires a prior browser.open step")
        if text is not None:
            return self._page.get_by_text(text, exact=exact).first
        if role is not None and accessible_name is not None:
            return self._page.get_by_role(role, name=accessible_name, exact=exact).first
        if test_id is not None:
            return self._page.get_by_test_id(test_id).first
        raise RitualistError("browser action requires a structured target")


def _dismiss_known_restore_prompt(page: Any) -> bool:
    # Playwright page locators address web content, not browser chrome. A page can
    # legitimately contain "Restore pages?" and a "Cancel" button, so clicking via
    # DOM locators would be unscoped prompt dismissal. Clean-start launch flags are
    # the supported prevention path until a browser-UI-scoped adapter exists.
    _ = page
    return False


def _locator_visible_quietly(locator: Any, *, timeout_seconds: float) -> bool:
    try:
        return _locator_visible(locator, timeout_seconds=timeout_seconds)
    except DependencyMissingError:
        raise
    except Exception:  # noqa: BLE001 - hidden/unsupported locators are a no-op here.
        return False


def _locator_visible(locator: Any, *, timeout_seconds: float) -> bool:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    except ImportError as exc:
        raise DependencyMissingError(
            "browser actions require Playwright; install ritualist[browser] and run "
            "'python -m playwright install chromium'"
        ) from exc
    try:
        locator.wait_for(state="visible", timeout=timeout_seconds * 1000)
    except PlaywrightTimeoutError:
        return False
    return True


def _profile_dir(*, browser: str, profile: str) -> Path:
    path = browser_profiles_dir() / browser / profile
    path.mkdir(parents=True, exist_ok=True)
    return path


def _redact_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return "[unavailable]"
    if not parts.scheme or not parts.netloc:
        return raw_url.split("?", 1)[0].split("#", 1)[0]
    try:
        port = parts.port
    except ValueError:
        return "[unavailable]"
    hostname = parts.hostname
    if not hostname:
        return "[unavailable]"
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parts.scheme, netloc, _safe_path(parts.path), "", ""))


def _safe_path(path: str) -> str:
    lowered = path.casefold()
    sensitive_markers = ("token", "secret", "password", "passwd", "credential", "session")
    if any(marker in lowered for marker in sensitive_markers):
        return "/[redacted]"
    return path
