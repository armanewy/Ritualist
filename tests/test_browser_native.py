from __future__ import annotations

import pytest

from ritualist.adapters.browser_native import NativeBrowserAdapter


def test_native_browser_adapter_uses_injected_os_handoff():
    calls = []

    def opener(url: str, *, new: int, autoraise: bool) -> bool:
        calls.append((url, new, autoraise))
        return True

    adapter = NativeBrowserAdapter(opener=opener)

    adapter.open_url("https://example.test/dashboard", new_window=True)

    assert calls == [("https://example.test/dashboard", 2, True)]


@pytest.mark.parametrize("url", ["ftp://example.test", "file:///tmp/index.html", "not-a-url"])
def test_native_browser_adapter_rejects_non_http_urls(url: str):
    adapter = NativeBrowserAdapter(opener=lambda *_args, **_kwargs: True)

    with pytest.raises(Exception, match="HTTP or HTTPS URL"):
        adapter.open_url(url)


def test_native_browser_adapter_reports_failed_handoff():
    adapter = NativeBrowserAdapter(opener=lambda *_args, **_kwargs: False)

    with pytest.raises(Exception, match="default browser handoff"):
        adapter.open_url("https://example.test")
