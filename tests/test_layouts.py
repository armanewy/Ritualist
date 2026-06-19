from __future__ import annotations

import json
from types import SimpleNamespace

from setpiece.errors import SetpieceError
from setpiece.layouts import load_layout, save_layout_snapshot
from setpiece.overlay import ScreenRect


class FakeWindowCaptureAdapter:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def find_window_region(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_save_and_load_layout_snapshot(tmp_path):
    adapter = FakeWindowCaptureAdapter(
        [
            SimpleNamespace(
                rect=ScreenRect(x=100, y=120, width=800, height=600),
                window_title="Editor - Project",
                monitor_id="DISPLAY1",
                monitor_index=0,
            )
        ]
    )

    saved = save_layout_snapshot(
        "workbench",
        [{"title_contains": "Editor", "process_name": "Code.exe"}],
        window_adapter=adapter,
        base_dir=tmp_path,
    )
    loaded = load_layout("workbench", base_dir=tmp_path)

    assert loaded == saved
    assert (tmp_path / "workbench.json").exists()
    assert adapter.calls == [
        {
            "title_contains": "Editor",
            "process_name": "Code.exe",
            "timeout_seconds": 0,
        }
    ]
    assert loaded is not None
    assert loaded.windows[0].bounds is not None
    assert loaded.windows[0].bounds.width == 800
    assert loaded.windows[0].monitor_id == "DISPLAY1"
    assert loaded.windows[0].monitor_index == 0


def test_save_layout_snapshot_keeps_missing_windows_best_effort(tmp_path):
    adapter = FakeWindowCaptureAdapter(
        [
            SetpieceError("window not found"),
            SimpleNamespace(
                rect=ScreenRect(x=0, y=0, width=640, height=480),
                window_title="Chat",
            ),
        ]
    )

    layout = save_layout_snapshot(
        "mixed",
        [
            {"title_contains": "Missing"},
            {"process_name": "chat.exe"},
        ],
        window_adapter=adapter,
        base_dir=tmp_path,
    )

    assert [window.capture_status for window in layout.windows] == ["missing", "captured"]
    assert layout.windows[0].match.title_contains == "Missing"
    assert layout.windows[0].bounds is None
    assert layout.windows[1].match.process_name == "chat.exe"
    assert layout.windows[1].bounds is not None
    assert len(adapter.calls) == 2


def test_layout_file_schema_is_stable(tmp_path):
    adapter = FakeWindowCaptureAdapter(
        [
            SimpleNamespace(
                rect=ScreenRect(x=1, y=2, width=300, height=200),
                window_title="Launcher",
                monitor=SimpleNamespace(id="MONITOR-A", index=1),
            )
        ]
    )

    save_layout_snapshot(
        "stable",
        [{"title_contains": "Launcher"}],
        window_adapter=adapter,
        base_dir=tmp_path,
    )

    payload = json.loads((tmp_path / "stable.json").read_text(encoding="utf-8"))

    assert payload == {
        "schema_version": 1,
        "layout_id": "stable",
        "windows": [
            {
                "match": {
                    "title_contains": "Launcher",
                    "process_name": None,
                },
                "bounds": {
                    "x": 1,
                    "y": 2,
                    "width": 300,
                    "height": 200,
                },
                "monitor_id": "MONITOR-A",
                "monitor_index": 1,
                "window_title": "Launcher",
                "capture_status": "captured",
            }
        ],
    }


def test_load_layout_returns_none_for_missing_file(tmp_path):
    assert load_layout("missing", base_dir=tmp_path) is None
