"""Structured logging configuration.

Configures structlog for JSON output (production) or pretty console output
(development). Bridges Python's stdlib logging so that existing
logging.getLogger(__name__) calls also go through structlog's processors.

Logs are written to stdout and captured by Docker Compose:
    docker compose logs -f backend
    docker compose logs -f worker
"""

import logging
import sys
from typing import Any

import structlog


def configure_logging(app_env: str = "development") -> None:
    """Configure structlog + stdlib to emit structured logs to stdout."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    if app_env == "development":
        renderer: Any = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace any existing handlers so we don't duplicate log lines.
    root.handlers = [handler]
    root.setLevel(logging.INFO)
