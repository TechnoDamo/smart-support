"""Structured logging configuration with Graylog GELF support."""

from __future__ import annotations

import json
import logging
import socket
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

from pythonjsonlogger.json import JsonFormatter

from app.config import get_settings

# Context variables for request-scoped data
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
endpoint_var: ContextVar[Optional[str]] = ContextVar("endpoint", default=None)
STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
}


class GELFHandler(logging.Handler):
    """Graylog Extended Log Format (GELF) handler."""

    def __init__(self, host: str, port: int, protocol: str = "tcp"):
        super().__init__()
        self.host = host
        self.port = port
        self.protocol = protocol.lower()
        self.socket = None
        self._formatter = logging.Formatter()

    def connect(self):
        """Establish connection to Graylog."""
        try:
            if self.protocol == "tcp":
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.host, self.port))
            elif self.protocol == "udp":
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            else:
                raise ValueError(f"Unsupported protocol: {self.protocol}")
        except Exception as e:
            self.socket = None
            print(
                f"Failed to connect to Graylog at {self.host}:{self.port}: {e}",
                file=sys.stderr,
            )

    def emit(self, record: logging.LogRecord):
        """Send log record to Graylog."""
        if self.socket is None:
            self.connect()
            if self.socket is None:
                return

        try:
            # Convert log record to GELF format
            gelf_message = self._record_to_gelf(record)
            message_bytes = (json.dumps(gelf_message) + "\n").encode("utf-8")

            if self.protocol == "tcp":
                self.socket.sendall(message_bytes)
            else:  # UDP
                self.socket.sendto(message_bytes, (self.host, self.port))
        except Exception as e:
            print(f"Failed to send log to Graylog: {e}", file=sys.stderr)
            self.socket = None

    def _record_to_gelf(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Convert log record to GELF format."""
        # Base GELF fields
        gelf = {
            "version": "1.1",
            "host": socket.gethostname(),
            "short_message": record.getMessage(),
            "timestamp": record.created,
            "level": self._severity_to_syslog(record.levelno),
            "_logger": record.name,
            "_module": record.module,
            "_function": record.funcName,
            "_line": record.lineno,
        }

        # В стандартном logging extra-поля попадают прямо в __dict__ записи.
        for key, value in record.__dict__.items():
            if key in STANDARD_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            gelf[f"_{key}"] = self._normalize_value(value)

        # Add context variables
        request_id = request_id_var.get()
        if request_id:
            gelf["_request_id"] = request_id

        user_id = user_id_var.get()
        if user_id:
            gelf["_user_id"] = user_id

        endpoint = endpoint_var.get()
        if endpoint:
            gelf["_endpoint"] = endpoint

        # Add exception info
        if record.exc_info:
            gelf["_exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self._formatter.formatException(record.exc_info),
            }

        return gelf

    def _normalize_value(self, value: Any) -> Any:
        """Приводит extra-поле к JSON-сериализуемому виду для GELF."""
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    def _severity_to_syslog(self, level: int) -> int:
        """Convert Python logging level to syslog severity."""
        if level >= logging.CRITICAL:
            return 2  # CRITICAL
        elif level >= logging.ERROR:
            return 3  # ERROR
        elif level >= logging.WARNING:
            return 4  # WARNING
        elif level >= logging.INFO:
            return 6  # INFO
        else:
            return 7  # DEBUG

    def close(self):
        """Close the socket connection."""
        if self.socket:
            self.socket.close()
        super().close()


class StructuredJsonFormatter(JsonFormatter):
    """Custom JSON formatter with context support."""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ):
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO format
        log_record["timestamp"] = (
            datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        )

        # Add service identifier
        log_record["service"] = "smart-support-backend"

        # Add environment
        settings = get_settings()
        log_record["environment"] = settings.app_env

        # Add context variables
        request_id = request_id_var.get()
        if request_id:
            log_record["request_id"] = request_id

        user_id = user_id_var.get()
        if user_id:
            log_record["user_id"] = user_id

        endpoint = endpoint_var.get()
        if endpoint:
            log_record["endpoint"] = endpoint

        # Add exception info
        if record.exc_info:
            log_record["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }


def mask_sensitive_data(data: Any) -> Any:
    """Mask sensitive data in logs."""
    if isinstance(data, dict):
        masked = {}
        sensitive_keys = {
            "password",
            "token",
            "secret",
            "key",
            "authorization",
            "api_key",
            "access_key",
        }
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                masked[key] = "***MASKED***"
            else:
                masked[key] = mask_sensitive_data(value)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    elif isinstance(data, str) and len(data) > 100:
        # Truncate long strings
        return data[:100] + "..."
    else:
        return data


def setup_logging():
    """Configure logging for the application."""
    settings = get_settings()

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        console_handler.setFormatter(StructuredJsonFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    root_logger.addHandler(console_handler)

    # Graylog handler (if enabled)
    if getattr(settings, "graylog_enabled", False):
        try:
            graylog_host = getattr(settings, "graylog_host", "localhost")
            graylog_port = getattr(settings, "graylog_port", 12201)
            graylog_protocol = getattr(settings, "graylog_protocol", "tcp")

            graylog_handler = GELFHandler(graylog_host, graylog_port, graylog_protocol)
            graylog_handler.setLevel(getattr(logging, settings.log_level.upper()))
            root_logger.addHandler(graylog_handler)

            logger = logging.getLogger(__name__)
            logger.info(
                "Graylog logging enabled",
                extra={"graylog_host": graylog_host, "graylog_port": graylog_port},
            )
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to setup Graylog logging: {e}")

    # Raw SQL statements are too noisy for day-to-day work. We keep engine logs
    # quiet unless the whole app is explicitly in DEBUG mode.
    sqlalchemy_level = (
        logging.INFO if settings.log_level.upper() == "DEBUG" else logging.WARNING
    )
    logging.getLogger("sqlalchemy.engine").setLevel(sqlalchemy_level)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Keep access logs visible in normal operation so Graylog shows the full
    # HTTP picture alongside our middleware logs.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    # Suppress especially noisy third-party client logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with context support."""
    return logging.getLogger(name)


class RequestContext:
    """Context manager for request-scoped logging."""

    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id
        self.endpoint = endpoint
        self._request_token = None
        self._user_token = None
        self._endpoint_token = None

    def __enter__(self):
        self._request_token = request_id_var.set(self.request_id)
        if self.user_id:
            self._user_token = user_id_var.set(self.user_id)
        if self.endpoint:
            self._endpoint_token = endpoint_var.set(self.endpoint)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        request_id_var.reset(self._request_token)
        if self._user_token:
            user_id_var.reset(self._user_token)
        if self._endpoint_token:
            endpoint_var.reset(self._endpoint_token)


# Initialize logging when module is imported
setup_logging()
