"""
Centralized logging configuration module.

Provides structured JSON logging, correlation IDs, and environment-based configuration.
"""
import logging
import json
import contextvars
import os
from datetime import datetime
from typing import Optional, Any, Dict
from logging.handlers import RotatingFileHandler


# Context variable for correlation ID (set by middleware)
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id', default=None
)


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format with standard fields:
    - timestamp: ISO format timestamp
    - level: Log level name
    - logger: Logger name
    - message: Log message
    - correlation_id: Request correlation ID (if available)
    - service: Service name
    - extra_fields: Any additional context
    """

    def __init__(self, service_name: str = "unknown"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        # Base log data
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        # Add correlation ID from context
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
            'message', 'taskName'
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                try:
                    # Ensure value is JSON serializable
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data, ensure_ascii=False)


class CorrelationIdFilter(logging.Filter):
    """
    Filter that adds correlation_id to log records.

    Extracts correlation ID from context variable and adds it to each log record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id to the log record."""
        record.correlation_id = correlation_id_var.get() or "N/A"
        return True


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter for development mode.

    Format: timestamp - level - logger - [correlation_id] - message
    """

    def __init__(self, service_name: str = "unknown"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        correlation_id = correlation_id_var.get() or "N/A"

        # Base message
        message = f"{timestamp} - {record.levelname:8} - {record.name} - [{correlation_id}] - {record.getMessage()}"

        # Add exception if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_logging(
    service_name: str,
    log_level: str = "INFO",
    json_enabled: bool = True,
    log_file: Optional[str] = None
) -> None:
    """
    Configure logging for the application.

    Args:
        service_name: Name of the service (e.g., "public_api", "admin_api", "telegram_bot")
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_enabled: If True, use JSON format; otherwise use human-readable format
        log_file: Optional path to log file for file-based logging
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter based on configuration
    if json_enabled:
        formatter = JSONFormatter(service_name=service_name)
    else:
        formatter = TextFormatter(service_name=service_name)

    # Create correlation ID filter
    correlation_filter = CorrelationIdFilter()

    # Console handler (stdout)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(correlation_filter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        # Get rotation settings from environment
        max_bytes = int(os.getenv('LOG_FILE_MAX_SIZE', '10485760'))  # 10MB default
        backup_count = int(os.getenv('LOG_FILE_BACKUP_COUNT', '5'))

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(correlation_filter)
        root_logger.addHandler(file_handler)

    # Configure third-party library logging levels
    # Reduce noise from verbose libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    # Log initial setup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured for {service_name}",
        extra={
            "log_level": log_level,
            "json_enabled": json_enabled,
            "log_file": log_file or "none"
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID in the context.

    Args:
        correlation_id: The correlation ID to set
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """
    Get the current correlation ID from the context.

    Returns:
        Current correlation ID or None
    """
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """Clear the correlation ID from the context."""
    correlation_id_var.set(None)
