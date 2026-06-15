from __future__ import annotations

import threading

import pytest

from ritualist.runtime_control import RuntimeControl, RuntimeStoppedError


def test_pause_sets_paused() -> None:
    control = RuntimeControl()

    control.pause()

    assert control.is_paused()


def test_resume_clears_paused() -> None:
    control = RuntimeControl()
    control.pause()

    control.resume()

    assert not control.is_paused()


def test_stop_sets_stopping() -> None:
    control = RuntimeControl()

    control.stop()

    assert control.is_stopping()


def test_wait_if_paused_blocks_until_resume() -> None:
    control = RuntimeControl()
    control.pause()
    entered = threading.Event()
    released = threading.Event()

    def wait_for_resume() -> None:
        entered.set()
        control.wait_if_paused()
        released.set()

    thread = threading.Thread(target=wait_for_resume)
    thread.start()

    try:
        assert entered.wait(timeout=1.0)
        assert not released.wait(timeout=0.05)
    finally:
        control.resume()

    assert released.wait(timeout=1.0)
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_raise_if_stopped_raises() -> None:
    control = RuntimeControl()
    control.stop()

    with pytest.raises(RuntimeStoppedError, match="runtime stopped"):
        control.raise_if_stopped()
