"""Structured logging setup shared by all microservices.

Usage in any service's app/core/logging.py:

    from verve_vero_common.logging import setup_logging, log

Or call setup_logging directly in main.py:

    from verve_vero_common.logging import setup_logging
    setup_logging(level=settings.LOG_LEVEL, silence_noisy_loggers=True)
"""

import logging
import sys
from typing import Sequence

import structlog

from verve_vero_common.middleware.auth import UvicornHealthCheckFilter

# Default noisy loggers to silence (common in AWS SDK services)
DEFAULT_NOISY_LOGGERS = ("botocore", "boto3", "urllib3", "s3transfer")


def setup_logging(
    level: str = "INFO",
    silence_noisy_loggers: bool = False,
    extra_noisy_loggers: Sequence[str] = (),
):
    """Configure structlog JSON logging with health check filtering.

    Args:
        level: Log level string (INFO, DEBUG, WARNING, ERROR).
        silence_noisy_loggers: If True, suppress botocore/boto3/urllib3/s3transfer.
        extra_noisy_loggers: Additional logger names to silence.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Filter health check noise from uvicorn access logs
    logging.getLogger("uvicorn.access").addFilter(UvicornHealthCheckFilter())

    # Silence noisy libraries
    if silence_noisy_loggers:
        for name in DEFAULT_NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
    for name in extra_noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()
