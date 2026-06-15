from __future__ import annotations

from typing import Any

from ritualist.errors import DependencyMissingError, RitualistError


class PlaywrightBrowserAdapter:
    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def open_url(self, url: str, *, browser: str = "chromium") -> None:
        page = self._ensure_page(browser)
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
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    def _ensure_page(self, browser: str) -> Any:
        if self._page is not None:
            return self._page

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DependencyMissingError(
                "browser actions require Playwright; install ritualist[browser] and run "
                "'python -m playwright install chromium'"
            ) from exc

        self._playwright = sync_playwright().start()
        launch_options: dict[str, Any] = {"headless": False}
        if browser == "chrome":
            launch_options["channel"] = "chrome"
        elif browser == "msedge":
            launch_options["channel"] = "msedge"
        elif browser != "chromium":
            raise RitualistError(f"unsupported browser '{browser}'")

        self._browser = self._playwright.chromium.launch(**launch_options)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        return self._page
