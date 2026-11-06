"""
core/logger.py
--------------
Lightweight, thread-safe, high-performance logger with ANSI color formatting
for terminal output and daily rotating log files.
"""

from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from typing import Optional

# ANSI Colors
_COLORS = {
    "DEBUG": "\033[36m",       # Cyan
    "INFO": "\033[32m",        # Green
    "WARNING": "\033[33m",     # Yellow
    "ERROR": "\033[31m",       # Red
    "CRITICAL": "\033[1;31m",  # Bold Red
}
_RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    """Custom Formatter applying ANSI colors to terminal logs."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _RESET)
        time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        lvl = f"{record.levelname:<7}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{time_str} [{record.name}] {color}{lvl}{_RESET}: {msg}"


class PlainFormatter(logging.Formatter):
    """Clean Formatter for disk log files (strips ANSI color codes)."""

    def format(self, record: logging.LogRecord) -> str:
        time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        lvl = f"{record.levelname:<7}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{time_str} [{record.name}] {lvl}: {msg}"


_INITIALIZED = False


def configure_logger(
    project_name: str = "app",
    project_root: Optional[Path] = None,
    show_logs_on_terminal: bool = True,
    store_logs_in_file: bool = True,
    log_level: str = "INFO",
) -> logging.Logger:
    """Configures the root logging handlers for terminal and disk persistence."""
    global _INITIALIZED
    root = logging.getLogger()
    level = getattr(logging, log_level.upper(), logging.INFO)
    root.setLevel(level)

    # Clear existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    # 1. Terminal Console Handler
    if show_logs_on_terminal:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter())
        root.addHandler(console_handler)

    # 2. Daily Disk File Handler
    if store_logs_in_file and project_root:
        today_str = datetime.now().strftime("%Y-%m-%d")
        log_dir = Path(project_root) / "logs" / today_str
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / f"{project_name}.log"

        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=20 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(PlainFormatter())
        root.addHandler(file_handler)

    _INITIALIZED = True
    return logging.getLogger(project_name)


def get_logger(name: str) -> logging.Logger:
    """Returns a named logger instance."""
    global _INITIALIZED
    if not _INITIALIZED and not logging.getLogger().handlers:
        configure_logger(show_logs_on_terminal=True, store_logs_in_file=False)
    return logging.getLogger(name)
