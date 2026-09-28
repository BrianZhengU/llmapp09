"""Structured (JSON) logging to stdout and a rotating log file.

Every record carries the current request_id, so all log lines of one API call
(request, LLM calls, response) can be correlated.
"""
import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.getenv("LOG_FILE", "llm-multiroute.log")
# Prompts/outputs can contain personal data. Keep this off outside local debugging.
LOG_PROMPTS = os.getenv("LOG_PROMPTS", "false").lower() == "true"

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        # Anything passed via logger.info(..., extra={...}) becomes a JSON field.
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging() -> None:
    formatter = JsonFormatter()
    handlers: list = [logging.StreamHandler(sys.stdout)]
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                os.path.join(LOG_DIR, LOG_FILE), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
            )
        )
    except OSError:
        pass  # read-only filesystem (e.g. some containers): stdout only

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(LOG_LEVEL)
    # Our middleware logs every request; silence uvicorn's duplicate access log.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
