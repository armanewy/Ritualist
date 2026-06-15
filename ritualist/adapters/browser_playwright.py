from __future__ import annotations

from pathlib import Path
from typing import Any

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

    def open_url(
        self,
        url: str,
        *,
        browser: str = "chromium",
        profile: str = "default",
        new_window: bool = False,
    ) -> None:
        page = self._ensure_page(browser=browser, profile=profile, new_window=new_window)
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

    def _ensure_page(self, *, browser: str, profile: str, new_window: bool) -> Any:
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


def _profile_dir(*, browser: str, profile: str) -> Path:
    path = browser_profiles_dir() / browser / profile
    path.mkdir(parents=True, exist_ok=True)
    return path
