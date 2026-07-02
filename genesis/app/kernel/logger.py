"""Logging setup for the Genesis kernel."""

from __future__ import annotations

import logging
import sys


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str = "INFO", *, force: bool = False) -> logging.Logger:
    """Configure process logging and return the kernel logger."""

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=normalized_level,
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=force,
    )
    logger = logging.getLogger("genesis.kernel")
    logger.setLevel(normalized_level)
    return logger
