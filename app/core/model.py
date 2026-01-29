"""Core text model structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ProtectedSpan:
    """Represents a protected span in the text."""

    start: int
    end: int
    label: str
    source: str


@dataclass(frozen=True)
class Token:
    """Represents a token with offsets."""

    text: str
    start: int
    end: int
    is_protected: bool = False


@dataclass(frozen=True)
class Edit:
    """Represents a candidate or applied edit."""

    start: int
    end: int
    before: str
    after: str
    edit_type: str
    confidence: float
    stage: str
    safe_reason: str


@dataclass
class AuditLog:
    """Captures applied/rejected edits and rollback events."""

    applied_edits: List[Edit] = field(default_factory=list)
    rejected_edits: List[Edit] = field(default_factory=list)
    rollbacks: List[str] = field(default_factory=list)


@dataclass
class TextDocument:
    """Holds the text during processing."""

    raw_text: str
    working_text: str
    tokens: List[Token] = field(default_factory=list)
    protected_spans: List[ProtectedSpan] = field(default_factory=list)
    placeholders_map: Dict[str, str] = field(default_factory=dict)
    audit_log: AuditLog = field(default_factory=AuditLog)
    confidence: Optional[float] = None
