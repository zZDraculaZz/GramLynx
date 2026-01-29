"""Guardrails rollback tests."""
from __future__ import annotations

from app.core.model import TextDocument
from app.core.policy import get_policy
from app.core.stages.base import StageContext
from app.core.stages.s6_guardrails import guardrails_check
from app.core.observability import Metrics


def test_guardrails_rollback_on_missing_placeholder() -> None:
    document = TextDocument(raw_text="Исходный", working_text="Очистка")
    document.placeholders_map = {"⟦PZ0⟧": "123"}
    context = StageContext(
        document=document,
        policy=get_policy("strict"),
        correlation_id="test",
        metrics=Metrics(),
    )
    guardrails_check(context)
    assert context.document.working_text == "Исходный"
    assert "placeholders_missing" in context.document.audit_log.rollbacks
