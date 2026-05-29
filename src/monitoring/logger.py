import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger(name: str, log_file: str, level=logging.INFO):
    """Create a rotating file logger that also writes to stdout.

    Creates the logs/ directory if it does not exist. Resets handlers on
    repeated calls so the same logger name can be re-initialised safely.

    Args:
        name: Logger name (used as the %(name)s field in log lines).
        log_file: Filename within the logs/ directory (e.g. "trading_bot.log").
        level: Logging level; defaults to INFO.

    Returns:
        Configured logging.Logger instance.
    """
    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    log_path = os.path.join("logs", log_file)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8"
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Always reset handlers to avoid duplicates 
    logger.handlers = []

    # File handler 
    logger.addHandler(handler)

    # Console handler (stdout) 
    console_handler = logging.StreamHandler() 
    console_handler.setFormatter(formatter) 
    logger.addHandler(console_handler)

    return logger
