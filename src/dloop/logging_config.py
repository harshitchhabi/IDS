"""Structured logging setup.

CLAUDE.md requires structured logging (JSON), never ``print`` — "I need to see
what got dropped during cleaning." Every module gets a logger via
:func:`get_logger`; call :func:`configure` once at process entry.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

_CONFIGURED = False


def configure(level: str | int | None = None, *, json: bool | None = None) -> None:
    """Configure structlog + stdlib logging for the process.

    Idempotent. ``level`` defaults to ``$DLOOP_LOG_LEVEL`` or ``INFO``. ``json``
    defaults to ``$DLOOP_LOG_JSON`` (truthy) or, when unset, JSON off for a TTY
    and on otherwise, so interactive runs stay readable while pipeline runs stay
    machine-parseable.
    """
    global _CONFIGURED

    if level is None:
        level = os.environ.get("DLOOP_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())
    if json is None:
        env = os.environ.get("DLOOP_LOG_JSON")
        json = env.lower() in {"1", "true", "yes"} if env is not None else not sys.stderr.isatty()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=level)
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, configuring with defaults on first use."""
    if not _CONFIGURED:
        configure()
    return structlog.get_logger(name)
