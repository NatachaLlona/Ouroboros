"""Reusable, single-line console and daily file logging."""
import inspect
from contextvars import ContextVar
import json
import logging
import sys
import secrets
from pathlib import Path

from app.config import LEVELS, PROJECT_ROOT, validate_logging
from app.request_context import request_context
from app.log_safety import redact
from app.console import prepare_console, LevelColorFormatter
from app.cleanup import cleanup_actions, ResourceCleanupError
from app.datetimes import utcnow, from_timestamp


def clean(value):
    """Escape untrusted control characters, including Unicode line separators."""
    text = str(value)
    return "".join(f"\\u{ord(char):04x}" if ord(char) < 32 or
                   127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF or char in "\u2028\u2029" else char
                   for char in text)


class EventFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return from_timestamp(record.created).isoformat(timespec="milliseconds")

    def format(self, record):
        record.datetime = self.formatTime(record)
        return clean(super().format(record))


RUN_ID = utcnow().strftime("%H%M%S") + "_" + secrets.token_hex(4)


class DailyFileHandler(logging.Handler):
    """Append events to the file matching their local calendar date."""
    def __init__(self, directory):
        super().__init__()
        self.stream = None
        self.day = None
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def emit(self, record):
        day = from_timestamp(record.created).date().isoformat()
        if self.day != day:
            if self.stream is not None:
                self.stream.close()
            self.stream = (self.directory / f"application_{day}_{RUN_ID}.log").open("a", encoding="utf-8")
            self.day = day
        self.stream.write(self.format(record) + "\n")
        self.stream.flush()

    def close(self):
        self.acquire()
        try:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            super().close()
        finally:
            self.release()


class ApplicationLogger:
    """Accept JSON-compatible event dictionaries; callers must omit secrets."""
    def __init__(self, config, component="ouroboros", root=PROJECT_ROOT, stream=None):
        validate_logging(config)
        self.root = Path(root).resolve()
        self.config = dict(config)
        # An owned logger avoids global handler accumulation and cross-instance interference.
        self.logger = logging.Logger(clean(component), LEVELS[config["level"]])
        self.logger.propagate = False
        formatter = EventFormatter(config["format"])
        try:
            console_stream = stream if stream is not None else prepare_console(sys.stderr)
            console = logging.StreamHandler(console_stream)
            self.logger.addHandler(console)
            directory = Path(config["directory"])
            self.logger.addHandler(DailyFileHandler(self.root / directory))
            console.setFormatter(LevelColorFormatter(formatter, console_stream))
            self.logger.handlers[1].setFormatter(formatter)
        except BaseException:
            try:
                self.close()
            except BaseException:
                pass
            raise

    def log(self, event, *, stacklevel=1):
        if not isinstance(event, dict):
            raise ValueError("Log event must be a JSON-compatible dictionary")
        try:
            json.dumps(event, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError("Log event must be JSON-compatible") from error
        level = event.get("level", "INFO")
        if not isinstance(level, str) or level not in LEVELS:
            raise ValueError("Event level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        if not isinstance(event.get("message"), str):
            raise ValueError("Event message must be a string")
        interaction = event.get("interaction_id")
        if interaction is not None and not isinstance(interaction, str):
            raise ValueError("interaction_id must be a string or null")
        if not self.logger.isEnabledFor(LEVELS[level]):
            return
        context = request_context.get()
        frame = inspect.currentframe().f_back
        for _ in range(stacklevel - 1):
            frame = frame.f_back
        try:
            path = Path(frame.f_code.co_filename).resolve()
            try:
                source = path.relative_to(self.root).as_posix()
            except ValueError:
                source = path.as_posix()
            instance = frame.f_locals.get("self")
            caller_class = type(instance).__name__ if instance is not None else "-"
            if instance is None and isinstance(frame.f_locals.get("cls"), type):
                caller_class = frame.f_locals["cls"].__name__
            record = self.logger.makeRecord(
                self.logger.name, LEVELS[level], str(path), frame.f_lineno,
                clean(event["message"]), (), None,
                extra={"level": level, "component": clean(event.get("component", self.logger.name)),
                       "class_name": clean(caller_class), "source": clean(source),
                       "line": frame.f_lineno,
                       "interaction_id": context.interaction_id if context else "",
                       "category": "request" if context else "application",
                       "method": clean(context.method) if context else "",
                       "path": clean(context.path) if context else "",
                       "method_path": clean(context.method + " " + context.path) if context else "",
                       "context": clean(json.dumps(redact(event.get("context", {})), ensure_ascii=False, allow_nan=False))})
        finally:
            del frame
        self.logger.handle(record)

    def close(self):
        handlers = self.logger.handlers[:]
        failures = cleanup_actions([(f"log_handler_{index}", handler.close) for index, handler in enumerate(handlers)])
        for handler in handlers:
            self.logger.removeHandler(handler)
        if failures:
            raise ResourceCleanupError(failures)


active_logger = ContextVar("foundation_active_logger", default=None)


def log_event(level, message, context=None, component=None):
    logger = active_logger.get()
    if logger is not None:
        logger.log({"level": level, "message": message, "context": context or {},
                    "component": component or logger.logger.name}, stacklevel=2)
