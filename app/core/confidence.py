"""Document confidence aggregation."""
from __future__ import annotations

from app.core.model import TextDocument


def aggregate_confidence(document: TextDocument) -> float:
    """Aggregate confidence from applied edits. Defaults to 1.0 if none."""
    if not document.audit_log.applied_edits:
        return 1.0
    return min(edit.confidence for edit in document.audit_log.applied_edits)
