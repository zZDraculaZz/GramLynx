"""Simple observability helpers."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class Metrics:
    """In-memory metrics container."""

    requests_total: Dict[str, int] = field(default_factory=dict)
    stage_duration_ms: Dict[Tuple[str, str], float] = field(default_factory=dict)
    edits_applied_total: Dict[Tuple[str, str], int] = field(default_factory=dict)
    edits_rejected_total: Dict[Tuple[str, str], int] = field(default_factory=dict)
    rollbacks_total: Dict[str, int] = field(default_factory=dict)
    protected_spans_total: Dict[str, int] = field(default_factory=dict)


def get_correlation_id(header_value: str | None) -> str:
    """Get correlation id from header or generate one."""

    return header_value or str(uuid.uuid4())


def log_event(**payload: object) -> None:
    """Emit a structured JSON log line."""

    print(json.dumps(payload, ensure_ascii=False))
