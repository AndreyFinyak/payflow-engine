import logging

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.logging.log_level_value,
        format=settings.logging.log_format,
        datefmt=settings.logging.log_datefmt,
    )
