from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in {
                "args",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }
        }
        payload.update(extras)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO",
    json_logs: bool = True,
    *,
    file_enabled: bool = False,
    log_dir: Path | None = None,
) -> logging.Logger:
    logger = logging.getLogger("repoagents")
    logger.setLevel(level.upper())
    _close_handlers(logger)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    if json_logs:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)

    if file_enabled:
        if log_dir is None:
            raise ValueError("log_dir is required when file_enabled=True")
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "repoagents.jsonl", encoding="utf-8")
        file_handler.setFormatter(JsonLogFormatter())
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def get_logger(name: str = "repoagents") -> logging.Logger:
    logger = logging.getLogger(name)
    _drop_closed_handlers(logger)
    current = name
    while "." in current:
        current = current.rsplit(".", 1)[0]
        _drop_closed_handlers(logging.getLogger(current))
    return logger


def _drop_closed_handlers(logger: logging.Logger) -> None:
    stale_handlers = []
    for handler in logger.handlers:
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            stale_handlers.append(handler)
    for handler in stale_handlers:
        logger.removeHandler(handler)


def _close_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
