from __future__ import annotations

from ritualist.event_coalescing import DEFAULT_TARGET_HZ, EventCoalescer


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_events_with_same_key_are_coalesced_to_latest_state():
    clock = FakeClock()
    coalescer = EventCoalescer(target_hz=60, clock=clock)

    coalescer.put("run:1", {"status": "starting"})
    coalescer.put("run:1", {"status": "running"})
    clock.advance(coalescer.interval_seconds)

    assert coalescer.emit_due() == {"run:1": {"status": "running"}}


def test_events_with_different_keys_are_preserved():
    clock = FakeClock()
    coalescer = EventCoalescer(target_hz=30, clock=clock)

    coalescer.put("run:1", {"status": "running"})
    coalescer.put("run:2", {"status": "stopped"})
    clock.advance(coalescer.interval_seconds)

    assert coalescer.emit_due() == {
        "run:1": {"status": "running"},
        "run:2": {"status": "stopped"},
    }


def test_flush_emits_pending_state_before_interval_elapsed():
    clock = FakeClock()
    coalescer = EventCoalescer(target_hz=60, clock=clock)

    coalescer.put("home", {"active_runs": 2})

    assert coalescer.emit_due() == {}
    assert coalescer.flush() == {"home": {"active_runs": 2}}
    assert not coalescer.has_pending


def test_helper_is_gui_independent_and_uses_deterministic_clock():
    clock = FakeClock()
    coalescer = EventCoalescer(clock=clock)

    coalescer.put("summary", "pending")
    clock.advance((1.0 / DEFAULT_TARGET_HZ) / 2)
    assert coalescer.emit_due() == {}

    clock.advance((1.0 / DEFAULT_TARGET_HZ) / 2)
    assert coalescer.emit_due() == {"summary": "pending"}
