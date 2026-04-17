from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "breakoutbolt.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt))

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[logging.StreamHandler(), file_handler],
    )
