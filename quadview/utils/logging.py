"""Bounded local JSON diagnostics without browsing data."""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone


class DiagnosticFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        document = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "event": record.getMessage(),
        }
        for key in ("state", "count", "window", "error_type", "command"):
            if hasattr(record, key):
                document[key] = getattr(record, key)
        return json.dumps(document, ensure_ascii=False)


def configure_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "quadview.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(DiagnosticFormatter())
    logger = logging.getLogger("quadview")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
