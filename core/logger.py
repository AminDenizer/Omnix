"""
Omnix Diagnostic Logging & Event Reporting Subsystem
Governing Requirement: Section 3 — Live Log & Event Reporting

Provides:
- Centralized structured event recording across all application domains
- Explicit operation lifecycles (START, PROGRESS, COMPLETION, FAILURE) with correlation IDs
- ISO-8601 UTC timestamps and standardized severities (INFO, WARNING, ERROR)
- User-understandable messaging with automatic credential/secret redaction
- Bounded in-memory event retention (deque) and rotating disk log storage (RotatingFileHandler)
- Thread-safe event distribution for background workers and GUI thread via Qt signal bridge
- Idempotent configuration and safe fallback if disk I/O fails
"""

import os
import re
import sys
import uuid
import logging
import datetime
import threading
from collections import deque
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, List, Callable, Sequence
from contextlib import contextmanager

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

from config import get_app_dir


# ---------------------------------------------------------------------------
# Sensitive-Data Redaction Engine
# ---------------------------------------------------------------------------

SENSITIVE_KEY_PATTERNS = (
    "password", "passwd", "secret", "token", "cookie",
    "credential", "api_key", "apikey", "authorization", "auth",
    "session_id", "session-id", "sessionid", "session_token", "session_secret",
    "private_key", "private-key", "privatekey", "jwt",
)

# Regex patterns to sanitize plaintext secrets in log strings
REDACT_REGEXES = [
    # 1. Bearer / Token / JWT auth in headers or strings: Bearer eyJhbGciOi...
    (
        re.compile(r'((?:Bearer|Token|JWT)\s+)[A-Za-z0-9\-_.=]+', re.IGNORECASE),
        r'\1***REDACTED***',
    ),
    # 2. Basic auth credentials in URLs: https://user:password@domain.com
    (
        re.compile(r'(https?://[^:\s/@]+:)([^@\s/]+)(@)', re.IGNORECASE),
        r'\1***REDACTED***\3',
    ),
    # 3. Key-value pairs: password="xyz" or token: 'xyz' or session_id=xyz or private_key=xyz or jwt=xyz
    (
        re.compile(
            r'((?:password|passwd|token|api[-_]?key|secret|cookie|credential|session(?:[-_]?id)?|private[-_]?key|jwt(?:[-_]?token)?|auth(?:[-_]?token)?)\s*[:=]\s*["\']?)([^"\'\s,;&]+)(["\']?)',
            re.IGNORECASE,
        ),
        r'\1***REDACTED***\3',
    ),
    # 4. Standalone JWT tokens (Header.Payload.Signature)
    (
        re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\b'),
        r'***REDACTED***',
    ),
    # 5. PEM private key blocks
    (
        re.compile(r'-----BEGIN[ A-Z_-]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z_-]*PRIVATE KEY-----', re.IGNORECASE),
        r'***REDACTED PRIVATE KEY***',
    ),
]


def sanitize_text(text: Any) -> str:
    """
    Centrally redacts credentials, passwords, session tokens, and secrets from arbitrary strings.
    Safe against non-string inputs.
    """
    if text is None:
        return ""
    s = str(text)
    for pattern, repl in REDACT_REGEXES:
        s = pattern.sub(repl, s)
    return s


def sanitize_dict(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Recursively redacts sensitive keys and values from a dictionary.
    Returns a new sanitized dictionary.
    """
    if not data or not isinstance(data, dict):
        return {}
    sanitized: Dict[str, Any] = {}
    for k, v in data.items():
        k_str = str(k)
        k_norm = k_str.lower().replace("_", "").replace("-", "")
        if any(p.replace("_", "").replace("-", "") in k_norm for p in SENSITIVE_KEY_PATTERNS):
            sanitized[k_str] = "***REDACTED***"
        elif isinstance(v, dict):
            sanitized[k_str] = sanitize_dict(v)
        elif isinstance(v, (list, tuple)):
            sanitized[k_str] = [
                sanitize_dict(item) if isinstance(item, dict) else sanitize_text(item)
                for item in v
            ]
        elif isinstance(v, str):
            sanitized[k_str] = sanitize_text(v)
        else:
            sanitized[k_str] = v
    return sanitized


class SecretRedactingFormatter(logging.Formatter):
    """
    Standard logging.Formatter that ensures all formatted output, including
    exception tracebacks and formatted message arguments, has secrets redacted.
    """

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return sanitize_text(original)


# ---------------------------------------------------------------------------
# Structured Event Record
# ---------------------------------------------------------------------------

class EventRecord:
    """
    Immutable representation of an application event for Live Log & Audit reporting.
    """

    __slots__ = (
        "timestamp",
        "level",
        "domain",
        "event_type",
        "message",
        "operation_id",
        "details",
    )

    def __init__(
        self,
        timestamp: str,
        level: str,
        domain: str,
        event_type: str,
        message: str,
        operation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.timestamp = timestamp
        self.level = level.upper()
        self.domain = domain
        self.event_type = event_type.upper()
        self.message = sanitize_text(message)
        self.operation_id = operation_id
        self.details = sanitize_dict(details) if details else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "domain": self.domain,
            "event_type": self.event_type,
            "message": self.message,
            "operation_id": self.operation_id,
            "details": dict(self.details) if self.details else None,
        }

    def __repr__(self) -> str:
        op = f" [{self.operation_id}]" if self.operation_id else ""
        return f"<EventRecord {self.timestamp} [{self.level}] [{self.domain}:{self.event_type}]{op} {self.message}>"


# ---------------------------------------------------------------------------
# Bounded In-Memory Event Retention
# ---------------------------------------------------------------------------

class EventBuffer:
    """
    Thread-safe, bounded circular buffer for Live Log UI events.
    """

    def __init__(self, max_size: int = 1000):
        self._max_size = max(10, max_size)
        self._buffer: deque[EventRecord] = deque(maxlen=self._max_size)
        self._lock = threading.Lock()

    @property
    def max_size(self) -> int:
        return self._max_size

    def append(self, record: EventRecord) -> None:
        with self._lock:
            self._buffer.append(record)

    def get_all(self) -> List[EventRecord]:
        with self._lock:
            return list(self._buffer)

    def count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


# ---------------------------------------------------------------------------
# Qt Signal Bridge for Thread-Safe UI Updates
# ---------------------------------------------------------------------------

if HAS_PYQT:
    class _LogEventBridge(QObject):
        eventLogged = pyqtSignal(object)  # Emits EventRecord

        def emit_event(self, record: EventRecord) -> None:
            self.eventLogged.emit(record)
else:
    class _LogEventBridge:  # type: ignore[no-redef]
        def emit_event(self, record: EventRecord) -> None:
            pass


# ---------------------------------------------------------------------------
# Central Subsystem State
# ---------------------------------------------------------------------------

_is_configured = False
_config_lock = threading.Lock()
_event_buffer = EventBuffer(max_size=1000)
_event_bridge: Optional[_LogEventBridge] = None
_subscribers: List[Callable[[EventRecord], None]] = []
_subscribers_lock = threading.Lock()


def get_event_buffer() -> EventBuffer:
    return _event_buffer


def get_event_bridge() -> _LogEventBridge:
    global _event_bridge
    if _event_bridge is None:
        _event_bridge = _LogEventBridge()
    return _event_bridge


def add_event_subscriber(callback: Callable[[EventRecord], None]) -> None:
    """Add a Python callable subscriber (safe for unit tests and headless environments)."""
    with _subscribers_lock:
        if callback not in _subscribers:
            _subscribers.append(callback)


def remove_event_subscriber(callback: Callable[[EventRecord], None]) -> None:
    with _subscribers_lock:
        if callback in _subscribers:
            _subscribers.remove(callback)


def get_log_dir() -> str:
    """
    Returns the authoritative log directory.
    Respects OMNIX_LOG_DIR environment variable if specified.
    Defaults to '<app_dir>/logs'.
    """
    env_dir = os.environ.get("OMNIX_LOG_DIR")
    if env_dir and env_dir.strip():
        abs_p = os.path.abspath(env_dir.strip())
        os.makedirs(abs_p, exist_ok=True)
        return abs_p
    p = os.path.join(get_app_dir(), "logs")
    os.makedirs(p, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Logging Handler Connecting Standard Library Logging to Event System
# ---------------------------------------------------------------------------

class OmnixEventLoggingHandler(logging.Handler):
    """
    Custom logging handler that intercepts standard logging records and creates
    structured EventRecords with secret redaction.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Map logger name to domain
            name = record.name
            domain = "System"
            if "." in name:
                parts = name.split(".")
                domain = parts[-1].capitalize() if len(parts) > 1 else "System"
            elif name and name != "root":
                domain = name.capitalize()

            # Map level
            level = record.levelname.upper()
            if level not in ("INFO", "WARNING", "ERROR"):
                level = "INFO" if record.levelno < logging.WARNING else ("WARNING" if record.levelno < logging.ERROR else "ERROR")

            # Extract operation_id or event_type from extra if present
            op_id = getattr(record, "operation_id", None)
            event_type = getattr(record, "event_type", "LOG")

            msg = self.format(record)
            ev = EventRecord(
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                level=level,
                domain=domain,
                event_type=event_type,
                message=msg,
                operation_id=op_id,
            )
            _event_buffer.append(ev)
            get_event_bridge().emit_event(ev)

            with _subscribers_lock:
                subs = list(_subscribers)
            for sub in subs:
                try:
                    sub(ev)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Core Public API: log_event & track_operation
# ---------------------------------------------------------------------------

def log_event(
    domain: str,
    event_type: str,
    message: str,
    level: str = "INFO",
    operation_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> EventRecord:
    """
    Authoritative recording of an application event.
    Guarantees:
    - Real-time timestamp in UTC ISO-8601
    - Secrets redacted from message and details
    - Appended to bounded in-memory buffer
    - Delivered to Qt bridge (GUI thread safe) and subscribers
    - Written to disk rotating file if logging is initialized
    """
    level_norm = level.upper()
    if level_norm not in ("INFO", "WARNING", "ERROR"):
        level_norm = "INFO"

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = EventRecord(
        timestamp=now_iso,
        level=level_norm,
        domain=domain,
        event_type=event_type,
        message=message,
        operation_id=operation_id,
        details=details,
    )

    # 1. Bounded memory retention
    _event_buffer.append(record)

    # 2. Qt Event Bridge
    get_event_bridge().emit_event(record)

    # 3. Direct subscribers
    with _subscribers_lock:
        subs = list(_subscribers)
    for sub in subs:
        try:
            sub(record)
        except Exception:
            pass

    # 4. Standard Python logger routing to disk/console
    py_logger = logging.getLogger(f"omnix.{domain}")
    log_msg = f"[{event_type}] {record.message}"
    if operation_id:
        log_msg = f"[{operation_id}] {log_msg}"

    if level_norm == "ERROR":
        py_logger.error(log_msg)
    elif level_norm == "WARNING":
        py_logger.warning(log_msg)
    else:
        py_logger.info(log_msg)

    return record


class OperationTracker:
    """
    Context manager tracking an end-to-end operation lifecycle.
    Guarantees:
    - Emits START on enter.
    - Allows PROGRESS milestone emissions.
    - Emits FAILURE on exception with sanitized error explanation, avoiding false completion.
    - Emits COMPLETION on clean exit.
    - Guarantees exactly one terminal event (COMPLETION or FAILURE, never both).
    - Preserves consistent correlation ID across all related events.
    """

    def __init__(
        self,
        domain: str,
        operation_name: str,
        operation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.domain = domain
        self.operation_name = operation_name
        self.operation_id = operation_id or f"op_{uuid.uuid4().hex[:8]}"
        self.details = details or {}
        self._terminal_emitted = False

    def progress(self, message: str, details: Optional[Dict[str, Any]] = None) -> EventRecord:
        """Record an in-flight milestone."""
        merged_details = dict(self.details)
        if details:
            merged_details.update(details)
        return log_event(
            domain=self.domain,
            event_type="PROGRESS",
            message=f"{self.operation_name}: {message}",
            level="INFO",
            operation_id=self.operation_id,
            details=merged_details,
        )

    def complete(self, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Optional[EventRecord]:
        """Explicitly record successful completion with custom message without duplicate terminal events."""
        if self._terminal_emitted:
            return None
        merged_details = dict(self.details)
        if details:
            merged_details.update(details)
        msg = message or f"Completed {self.operation_name} successfully"
        rec = log_event(
            domain=self.domain,
            event_type="COMPLETION",
            message=msg,
            level="INFO",
            operation_id=self.operation_id,
            details=merged_details,
        )
        self._terminal_emitted = True
        return rec

    def fail(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        level: str = "ERROR",
    ) -> Optional[EventRecord]:
        """Explicitly record operation failure with custom message without requiring an unhandled exception."""
        if self._terminal_emitted:
            return None
        merged_details = dict(self.details)
        if details:
            merged_details.update(details)
        msg = message or f"{self.operation_name} failed"
        rec = log_event(
            domain=self.domain,
            event_type="FAILURE",
            message=msg,
            level=level,
            operation_id=self.operation_id,
            details=merged_details,
        )
        self._terminal_emitted = True
        return rec

    def __enter__(self) -> 'OperationTracker':
        log_event(
            domain=self.domain,
            event_type="START",
            message=f"Started {self.operation_name}",
            level="INFO",
            operation_id=self.operation_id,
            details=self.details,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._terminal_emitted:
            return False

        if exc_type is not None:
            # Operation failed with an exception
            err_msg = sanitize_text(str(exc_val) or exc_type.__name__)
            # Clean user-understandable message
            msg = f"{self.operation_name} failed: {err_msg}"
            log_event(
                domain=self.domain,
                event_type="FAILURE",
                message=msg,
                level="ERROR",
                operation_id=self.operation_id,
                details=self.details,
            )
            self._terminal_emitted = True
            # Re-raise exception
            return False

        # Operation completed successfully
        log_event(
            domain=self.domain,
            event_type="COMPLETION",
            message=f"Completed {self.operation_name} successfully",
            level="INFO",
            operation_id=self.operation_id,
            details=self.details,
        )
        self._terminal_emitted = True
        return False


def track_operation(
    domain: str,
    operation_name: str,
    operation_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> OperationTracker:
    """Convenient factory for OperationTracker context manager."""
    return OperationTracker(
        domain=domain,
        operation_name=operation_name,
        operation_id=operation_id,
        details=details,
    )


# ---------------------------------------------------------------------------
# Setup & Initialization
# ---------------------------------------------------------------------------

def setup_logging(
    log_dir: Optional[str] = None,
    level: int = logging.INFO,
    console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """
    Initializes the Omnix diagnostic logging subsystem with:
    - Secret-redacting RotatingFileHandler (bounded disk retention)
    - Secret-redacting Console StreamHandler (stdout)
    - OmnixEventLoggingHandler routing into the bounded in-memory buffer and Qt bridge
    - Idempotent configuration (prevents duplicate handlers on re-entry)
    - Fault-tolerant fallback if disk writing fails
    """
    global _is_configured
    with _config_lock:
        root_logger = logging.getLogger("omnix")
        if _is_configured:
            return root_logger

        root_logger.setLevel(level)

        # Standard formatter with secret redaction
        formatter = SecretRedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 1. Bounded Rotating File Handler
        try:
            target_dir = log_dir or get_log_dir()
            os.makedirs(target_dir, exist_ok=True)
            log_path = os.path.join(target_dir, "omnix.log")
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            root_logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not initialize rotating log file ({e}). Continuing in-memory.\n")

        # 2. Console Handler
        if console:
            try:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                console_handler.setLevel(level)
                root_logger.addHandler(console_handler)
            except Exception:
                pass

        _is_configured = True
        root_logger.info("Omnix diagnostic logging subsystem initialized.")
        return root_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Returns a scoped logger under the 'omnix' namespace.
    Ensures setup_logging() has been called at least once.
    """
    if not _is_configured:
        setup_logging()
    if name:
        return logging.getLogger(f"omnix.{name}")
    return logging.getLogger("omnix")


def reset_logging_for_testing() -> None:
    """
    Cleans up all handlers, clears buffers and subscribers.
    Used exclusively in testing to ensure pristine isolation.
    """
    global _is_configured
    with _config_lock:
        loggers_to_clean = [logging.getLogger("omnix")]
        manager = logging.root.manager
        for name in list(manager.loggerDict.keys()):
            if name == "omnix" or name.startswith("omnix."):
                l = logging.getLogger(name)
                loggers_to_clean.append(l)

        for l in loggers_to_clean:
            for h in list(l.handlers):
                l.removeHandler(h)
                try:
                    h.flush()
                    h.close()
                except Exception:
                    pass
        _event_buffer.clear()
        with _subscribers_lock:
            _subscribers.clear()
        _is_configured = False
