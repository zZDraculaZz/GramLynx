"""Simple observability helpers."""
from __future__ import annotations

import json
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Dict, Tuple

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)


@dataclass
class Metrics:
    """In-memory metrics container."""

    requests_total: Dict[str, int] = field(default_factory=dict)
    stage_duration_ms: Dict[Tuple[str, str], float] = field(default_factory=dict)
    edits_applied_total: Dict[Tuple[str, str], int] = field(default_factory=dict)
    edits_rejected_total: Dict[Tuple[str, str], int] = field(default_factory=dict)
    rollbacks_total: Dict[str, int] = field(default_factory=dict)
    protected_spans_total: Dict[str, int] = field(default_factory=dict)


def set_request_id(value: str | None, token: Token[str | None] | None = None) -> Token[str | None] | None:
    """Set current request id in context, or reset by token."""

    if token is not None:
        _REQUEST_ID.reset(token)
        return None
    return _REQUEST_ID.set(value)


def get_request_id() -> str | None:
    """Get request id from context."""

    return _REQUEST_ID.get()


def get_correlation_id(header_value: str | None) -> str:
    """Get correlation id from header or generate one."""

    return header_value or str(uuid.uuid4())


def log_event(**payload: object) -> None:
    """Emit a structured JSON log line."""

    request_id = get_request_id()
    if request_id and "request_id" not in payload:
        payload["request_id"] = request_id
    print(json.dumps(payload, ensure_ascii=False))
