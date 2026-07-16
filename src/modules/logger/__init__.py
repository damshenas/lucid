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
    """Configure the root logger's handlers once (idempotent); the level is applied
    on *every* call, even after the first.

    This distinction matters: ``get_logger()`` is called at *import* time by many
    modules' own module-level ``_logger = get_logger(name)`` (bus, execution,
    schedules, com/*, ...) — which happens while ``src.api.main`` is still being
    imported, long before its ``_lifespan`` gets a chance to call this function with
    the real, resolved level (``LOG_LEVEL`` env var or the DB-backed
    ``logger.level`` setting). That implicit call configures with the default
    ``level="INFO"`` argument. If the level were only ever applied on the first call
    (guarded the same way as handler setup), that accidental import-time call would
    permanently lock the process at INFO — the later, real call from ``_lifespan``
    would be a silent no-op regardless of ``LOG_LEVEL``/``logger.level``. Handlers,
    on the other hand, must still only ever be added once (else every such call
    would duplicate every log line).
    """
    global _configured

    root = logging.getLogger()
    if not _configured:
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

    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def set_level(level: str) -> None:
    """Change the root logger's threshold live, without touching handlers.

    Unlike ``configure_logging`` (handlers/formatter set up once, at process start),
    this is safe to call any number of times — used so a ``logger.level`` change
    made via Settings takes effect immediately instead of requiring a restart (see
    ``save_values`` in src/api/v1/settings.py). Still subject to the same ``LOG_LEVEL``
    env var override precedence applied at startup (see src/api/main.py).
    """
    logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))


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
