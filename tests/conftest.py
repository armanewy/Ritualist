from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _reset_ritualist_logger_state():
    """Keep logger configuration from leaking between tests.

    Production logging intentionally installs handlers on the top-level
    ``ritualist`` logger and disables propagation. Several tests use pytest's
    caplog fixture against child loggers, so stale logger state from a previous
    test would otherwise make those records invisible in full-suite runs.
    """
    logger = logging.getLogger("ritualist")
    logger.handlers.clear()
    logger.propagate = True
    yield
    logger.handlers.clear()
    logger.propagate = True
