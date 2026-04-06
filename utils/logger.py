"""Logging configuration for BScraper."""

import logging
import json
import sys
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color coding to console output."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset to default
    }

    def format(self, record):
        """Format the log record with color coding on level name only."""
        # Basic timestamp and message from record
        timestamp = self.formatTime(record, self.datefmt)
        level = record.levelname
        message = record.getMessage()

        color = self.COLORS.get(level, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        level_colored = f"{color}{level}{reset}"

        # Keep message text uncolored (white/default)
        formatted = f"{timestamp} - {record.name} - {level_colored} - {message}"

        # Include exception info if present
        if record.exc_info:
            formatted = f"{formatted}\n{self.formatException(record.exc_info)}"

        return formatted


def setup_logger(name: str, log_file: str, level: str = "INFO") -> logging.Logger:
    """
    Set up a logger with both file and console handlers.
    Console output includes color coding for different log levels.

    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # File handler (no colors)
    fh = logging.FileHandler(log_file)
    fh.setLevel(getattr(logging, level.upper()))

    # Console handler (with colors)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, level.upper()))

    # Formatter for file (no colors)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(file_formatter)

    # Colored formatter for console
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    ch.setFormatter(console_formatter)

    # Add handlers
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger
