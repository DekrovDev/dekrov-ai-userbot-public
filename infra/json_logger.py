"""JSON-Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ñ‚ÐµÑ€ Ð´Ð»Ñ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ.

Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚Ð¸Ñ€ÑƒÐµÑ‚ Ð·Ð°Ð¿Ð¸ÑÐ¸ Ð»Ð¾Ð³Ð° Ð² JSON Ð´Ð»Ñ ÑƒÐ´Ð¾Ð±Ð½Ð¾Ð³Ð¾ Ð¿Ð°Ñ€ÑÐ¸Ð½Ð³Ð°.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON-Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ñ‚ÐµÑ€ Ð´Ð»Ñ ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ð¾Ð³Ð¾ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ.

    ÐŸÑ€Ð¸Ð¼ÐµÑ€ Ð²Ñ‹Ð²Ð¾Ð´Ð°:
        {
            "timestamp": "2026-03-28T10:30:00.123456+00:00",
            "level": "INFO",
            "logger": "assistant.main",
            "message": "config_loaded",
            "data": {
                "live_data_enabled": true,
                "strict_outgoing_only": true
            },
            "location": {
                "file": "main.py",
                "line": 81,
                "function": "run"
            }
        }

    Args:
        include_extra: Ð’ÐºÐ»ÑŽÑ‡Ð°Ñ‚ÑŒ Ð´Ð¾Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ðµ Ð¿Ð¾Ð»Ñ Ð¸Ð· record.__dict__
        include_location: Ð’ÐºÐ»ÑŽÑ‡Ð°Ñ‚ÑŒ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ Ð¼ÐµÑÑ‚Ðµ Ð²Ñ‹Ð·Ð¾Ð²Ð° (file, line, function)
    """

    def __init__(
        self,
        include_extra: bool = True,
        include_location: bool = False,
    ) -> None:
        super().__init__()
        self._include_extra = include_extra
        self._include_location = include_location

    def format(self, record: logging.LogRecord) -> str:
        """Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð·Ð°Ð¿Ð¸ÑÑŒ Ð»Ð¾Ð³Ð° Ð² JSON.

        Args:
            record: Ð—Ð°Ð¿Ð¸ÑÑŒ Ð»Ð¾Ð³Ð°

        Returns:
            JSON-ÑÑ‚Ñ€Ð¾ÐºÐ°
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ location ÐµÑÐ»Ð¸ Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾
        if self._include_location:
            payload["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ exception ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ extra-Ð¿Ð¾Ð»Ñ
        if self._include_extra:
            extra = self._extract_extra(record)
            if extra:
                payload["data"] = extra

        return json.dumps(payload, ensure_ascii=False, default=str)

    def _extract_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        """Ð˜Ð·Ð²Ð»ÐµÑ‡ÑŒ Ð´Ð¾Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ðµ Ð¿Ð¾Ð»Ñ Ð¸Ð· Ð·Ð°Ð¿Ð¸ÑÐ¸.

        Ð˜ÑÐºÐ»ÑŽÑ‡Ð°ÐµÑ‚ ÑÑ‚Ð°Ð½Ð´Ð°Ñ€Ñ‚Ð½Ñ‹Ðµ Ð°Ñ‚Ñ€Ð¸Ð±ÑƒÑ‚Ñ‹ LogRecord.
        """
        standard_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'exc_text',
            'filename', 'funcName', 'levelname', 'levelno', 'lineno',
            'module', 'msecs', 'message', 'msg', 'name', 'pathname',
            'process', 'processName', 'relativeCreated', 'stack_info',
            'thread', 'threadName', 'taskName', 'getMessage',
        }

        extra = {}
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                extra[key] = value

        return extra


def setup_json_logging(
    level: int = logging.INFO,
    log_file: str | None = None,
    include_location: bool = False,
) -> None:
    """ÐÐ°ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ JSON-Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ.

    Args:
        level: Ð£Ñ€Ð¾Ð²ÐµÐ½ÑŒ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
        log_file: ÐŸÑƒÑ‚ÑŒ Ðº Ñ„Ð°Ð¹Ð»Ñƒ Ð»Ð¾Ð³Ð° (Ð¾Ð¿Ñ†Ð¸Ð¾Ð½Ð°Ð»ÑŒÐ½Ð¾)
        include_location: Ð’ÐºÐ»ÑŽÑ‡Ð°Ñ‚ÑŒ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ Ð¼ÐµÑÑ‚Ðµ Ð²Ñ‹Ð·Ð¾Ð²Ð°
    """
    import sys
    from logging.handlers import RotatingFileHandler

    json_formatter = JsonFormatter(include_location=include_location)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(json_formatter)

    handlers = [console_handler]

    # File handler ÐµÑÐ»Ð¸ ÑƒÐºÐ°Ð·Ð°Ð½
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(json_formatter)
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True,
    )

