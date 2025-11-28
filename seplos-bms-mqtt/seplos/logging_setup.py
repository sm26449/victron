"""
Logging configuration with console and file support
"""

import logging
import os
from logging.handlers import RotatingFileHandler


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""

    def format(self, record):
        if record.levelno == logging.INFO:
            self._style._fmt = "%(asctime)-15s %(message)s"
        elif record.levelno == logging.DEBUG:
            self._style._fmt = "%(asctime)-15s \033[36m%(levelname)-8s\033[0m: %(message)s"
        else:
            color = {
                logging.WARNING: 33,
                logging.ERROR: 31,
                logging.FATAL: 31,
            }.get(record.levelno, 0)
            self._style._fmt = f"%(asctime)-15s \033[{color}m%(levelname)-8s %(threadName)-15s-%(module)-15s:%(lineno)-8s\033[0m: %(message)s"
        return super().format(record)


class PlainFormatter(logging.Formatter):
    """Plain formatter for file output (no colors)"""

    def format(self, record):
        if record.levelno == logging.INFO:
            self._style._fmt = "%(asctime)-15s %(message)s"
        else:
            self._style._fmt = "%(asctime)-15s %(levelname)-8s %(threadName)-15s-%(module)-15s:%(lineno)-8s: %(message)s"
        return super().format(record)


def setup_logging(log_level='INFO', log_file=None, max_bytes=5*1024*1024, backup_count=3):
    """
    Setup logging with optional file output

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (None to disable file logging)
        max_bytes: Maximum log file size before rotation (default 5MB)
        backup_count: Number of backup files to keep (default 3)

    Returns:
        Logger instance
    """
    log = logging.getLogger()
    log.handlers.clear()  # Clear any existing handlers

    # Set log level
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR
    }
    log.setLevel(log_levels.get(log_level.upper(), logging.INFO))

    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter())
    log.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        try:
            # Ensure log directory exists
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count
            )
            file_handler.setFormatter(PlainFormatter())
            log.addHandler(file_handler)
            log.info(f"File logging enabled: {log_file}")
        except Exception as e:
            log.warning(f"Could not enable file logging: {e}")

    return log


def get_logger():
    """Get the root logger instance"""
    return logging.getLogger()
