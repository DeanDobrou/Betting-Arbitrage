import logging
import sys
from pathlib import Path
from config.settings import settings


def setup_logger(name: str = None) -> logging.Logger:
    """
    Setup and configure logger with file and console handlers.

    Args:
        name: Logger name (use __name__ from calling module)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name or __name__)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )

    # File handler
    log_path = Path(settings.LOG_FILE)
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (use __name__ from calling module)

    Returns:
        Logger instance
    """
    return setup_logger(name)
