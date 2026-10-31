import logging as stdlib_logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """JSON lines to stderr; callers bind run_id and stage."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            stdlib_logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(**bound: object) -> structlog.typing.FilteringBoundLogger:
    return structlog.get_logger().bind(**bound)
