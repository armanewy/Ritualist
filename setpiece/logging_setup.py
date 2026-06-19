from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

from .paths import default_log_file


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    *,
    console: bool = False,
) -> logging.Logger:
    logger = logging.getLogger("setpiece")
    logger.setLevel(level.upper())
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_path = log_file or default_log_file()
    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = RichHandler(
            rich_tracebacks=False,
            markup=False,
            show_path=False,
            show_time=False,
        )
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console_handler)

    return logger
