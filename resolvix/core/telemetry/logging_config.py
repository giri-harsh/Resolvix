"""Structured JSON logs (§9.4, §8.1's `structlog`). Configures the stdlib root
logger through structlog's ProcessorFormatter so every `logging.getLogger(...)`
call already used across this codebase gets JSON output for free — a full rewrite
to structlog's own bound-logger API everywhere wasn't worth the token cost for
what's still a scope-cut demo, but the actual JSON-lines-on-stdout property holds.
"""
import logging
import sys

import structlog


def configure_logging() -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
