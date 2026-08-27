import logging

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.logging.level,
        log_format=settings.logging.log_format,
        datefmt=settings.logging.datefmt,
    )
