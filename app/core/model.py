"""Структуры внутренней модели текста."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ProtectedSpan:
    """Описывает защищённый фрагмент текста."""

    start: int
    end: int
    label: str
    source: str


@dataclass(frozen=True)
class Token:
    """Описывает токен с позициями в тексте."""

    text: str
    start: int
    end: int
    is_protected: bool = False


@dataclass(frozen=True)
class Edit:
    """Описывает кандидат или применённую правку."""

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
    """Журнал применённых/отклонённых правок и откатов."""

    applied_edits: List[Edit] = field(default_factory=list)
    rejected_edits: List[Edit] = field(default_factory=list)
    rollbacks: List[str] = field(default_factory=list)


@dataclass
class TextDocument:
    """Состояние текста во время обработки."""

    raw_text: str
    working_text: str
    tokens: List[Token] = field(default_factory=list)
    protected_spans: List[ProtectedSpan] = field(default_factory=list)
    placeholders_map: Dict[str, str] = field(default_factory=dict)
    audit_log: AuditLog = field(default_factory=AuditLog)
    confidence: Optional[float] = None
    safe_snapshot_text: Optional[str] = None
    safe_snapshot_placeholders: Dict[str, str] = field(default_factory=dict)
    safe_snapshot_spans: List[ProtectedSpan] = field(default_factory=list)
