"""Structured logging configuration for Datasheet Q&A Tool."""

import inspect
import json
import logging
import logging.handlers
from datetime import datetime, timezone

from . import config


class JsonFormatter(logging.Formatter):
    """Format log records as JSON objects for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "event": record.getMessage(),
        }

        # Include extra fields if present
        extra = getattr(record, "extra", None)
        if extra is not None:
            if isinstance(extra, dict):
                for key, value in extra.items():
                    if key not in ("ts", "level", "module", "function", "line", "event"):
                        try:
                            json.dumps(value)  # Validate JSON serializable
                            log_entry[key] = value
                        except (TypeError, ValueError):
                            log_entry[key] = str(value)

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class ContextualLogger:
    """Logger that supports structured extra data per log call."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def info(self, message: str, **extra) -> None:
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, **extra) -> None:
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, **extra) -> None:
        self._log(logging.ERROR, message, extra)

    def debug(self, message: str, **extra) -> None:
        self._log(logging.DEBUG, message, extra)

    def exception(self, message: str, **extra) -> None:
        self._log(logging.ERROR, message, extra, exc_info=True)

    def _log(
        self,
        level: int,
        message: str,
        extra_data: dict,
        exc_info: bool = False,
    ) -> None:
        # Capture caller info from stack: (frame, filename, lineno, function, code_context, index)
        frames = inspect.stack()
        caller_frame = frames[2]  # caller of info/warning/error/debug
        filepath = caller_frame[1]
        lineno = caller_frame[2]
        func_name = caller_frame[3]

        record = self.logger.makeRecord(
            self.logger.name,
            level,
            filepath,
            lineno,
            message,
            (),
            None,
            func=func_name,
        )
        if extra_data:
            record.extra = extra_data
        self.logger.handle(record)


def setup_logging() -> None:
    """Configure structured logging with console and rotating file handlers."""
    root_logger = logging.getLogger("datasheet_qa")
    root_logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on repeated calls
    if root_logger.handlers:
        return

    # Console handler — human-readable format, INFO+ only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.addFilter(_log_filter_info)
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler — JSON format, rotating, receives all levels
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(config.LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=config.LOG_MAX_BACKUPS,
        utc=True,
        delay=True,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> ContextualLogger:
    """Return a contextual logger for the given module name.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A ContextualLogger instance ready for structured logging.
    """
    return ContextualLogger(f"datasheet_qa.{name}")


def _log_filter_info(record: logging.LogRecord) -> bool:
    """Filter: only INFO+ goes to console, DEBUG stays in file."""
    return record.levelno >= logging.INFO