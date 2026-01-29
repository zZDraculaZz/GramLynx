"""Этап S6: guardrails и откат."""
from __future__ import annotations

from app.core.protected_zones.detector import placeholders_intact
from app.core.stages.base import StageContext


def guardrails_check(context: StageContext) -> None:
    """Проверяет инварианты и выполняет откат при нарушении."""

    if not placeholders_intact(
        context.document.working_text, context.document.placeholders_map
    ):
        context.document.working_text = context.document.raw_text
        context.document.audit_log.rollbacks.append("placeholders_missing")
