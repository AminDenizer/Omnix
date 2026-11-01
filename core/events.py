"""
Omnix Event Subsystem & Bus
Re-exports structured event entities and tracking utilities from core.logger.
"""

from core.logger import (
    EventRecord,
    EventBuffer,
    OperationTracker,
    log_event,
    track_operation,
    get_event_buffer,
    get_event_bridge,
    add_event_subscriber,
    remove_event_subscriber,
    sanitize_text,
    sanitize_dict,
)

__all__ = [
    "EventRecord",
    "EventBuffer",
    "OperationTracker",
    "log_event",
    "track_operation",
    "get_event_buffer",
    "get_event_bridge",
    "add_event_subscriber",
    "remove_event_subscriber",
    "sanitize_text",
    "sanitize_dict",
]
