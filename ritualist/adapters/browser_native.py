from __future__ import annotations

import webbrowser
from collections.abc import Callable
from urllib.parse import urlsplit

from ritualist.errors import RitualistError


class NativeBrowserAdapter:
    def __init__(self, opener: Callable[..., bool] | None = None) -> None:
        self._opener = opener or webbrowser.open

    def open_url(self, url: str, *, new_window: bool = False) -> None:
        _require_http_url(url)
        opened = self._opener(url, new=2 if new_window else 0, autoraise=True)
        if opened is False:
            raise RitualistError("default browser handoff was not accepted by the OS")


def _require_http_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise RitualistError("browser.open_native requires an HTTP or HTTPS URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RitualistError("browser.open_native requires an HTTP or HTTPS URL")
