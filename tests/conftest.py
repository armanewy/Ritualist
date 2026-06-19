from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

import pytest

from setpiece import paths


@pytest.fixture(autouse=True)
def _reset_setpiece_logger_state():
    """Keep logger configuration from leaking between tests.

    Production logging intentionally installs handlers on the top-level
    ``setpiece`` logger and disables propagation. Several tests use pytest's
    caplog fixture against child loggers, so stale logger state from a previous
    test would otherwise make those records invisible in full-suite runs.
    """
    logger = logging.getLogger("setpiece")
    logger.handlers.clear()
    logger.propagate = True
    yield
    logger.handlers.clear()
    logger.propagate = True


@pytest.fixture(autouse=True)
def _isolate_setpiece_app_paths(monkeypatch, request):
    """Keep tests from reading or writing the real user profile."""

    node_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)[-96:]
    isolated_root = (
        Path(tempfile.gettempdir()) / "setpiece-pytest-app-data" / str(os.getpid()) / node_slug
    )
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(isolated_root))
    paths._MIGRATION_ATTEMPTED = False
    yield
    paths._MIGRATION_ATTEMPTED = False
