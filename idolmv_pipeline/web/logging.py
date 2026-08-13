"""Centralised logging configuration for the Idol Video Studio pipeline."""

from __future__ import annotations

import logging
import sys


def configure(level: int = logging.INFO) -> None:
    """Configure the root logger with structured output."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Silence overly verbose third-party loggers
    for name in ("urllib3", "httpx", "httpcore", "seedance"):
        logging.getLogger(name).setLevel(logging.WARNING)
