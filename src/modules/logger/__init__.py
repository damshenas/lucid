"""Plain-text logging for Lucid.

Format: ``YYYY-MM-DD HH:MM:SS [LEVEL] module.name — message``

Rules (per plan.md):
- Plain text, simple formatter — not structured JSON.
- No client IP addresses anywhere.
- Health-check endpoints do not log (they use a level below the configured threshold).
- Log useful application events only, not every DB query or scheduler tick.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# A level below DEBUG used exclusively by health checks so they never appear in
# normal logs (default threshold is INFO).
TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_configured = False


def configure_logging(level: str = "INFO", file_path: str | None = None) -> None:
    """Configure the root logger once. Idempotent."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if file_path:
        try:
            file_handler = logging.FileHandler(file_path)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except (OSError, PermissionError):
            # Directory may not exist yet in local dev; stdout logging still works.
            root.warning("could not open log file %s — logging to stdout only", file_path)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Configures logging with defaults if not already done."""
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


def reset_for_tests() -> None:
    """Reset configuration state so tests can reconfigure cleanly."""
    global _configured
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    _configured = False
