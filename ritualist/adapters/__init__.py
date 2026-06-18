from __future__ import annotations

from ritualist.actions.base import AdapterBundle


def create_default_adapters() -> AdapterBundle:
    from .browser_native import NativeBrowserAdapter
    from .browser_playwright import PlaywrightBrowserAdapter
    from .shell import ShellAdapter
    from .window_manager import WindowsWindowManager
    from .windows_uia import WindowsInputAdapter, WindowsUIAutomationAdapter

    return AdapterBundle(
        shell=ShellAdapter(),
        browser=PlaywrightBrowserAdapter(),
        native_browser=NativeBrowserAdapter(),
        window=WindowsWindowManager(),
        desktop=WindowsUIAutomationAdapter(),
        input=WindowsInputAdapter(),
    )
