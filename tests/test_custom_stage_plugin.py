"""Тесты плагинной стадии и защитных ограничений."""
from __future__ import annotations

from app.core.model import TextDocument
from app.core.observability import Metrics
from app.core.policy import PolicyConfig
from app.core.protected_zones.detector import mask_protected_zones
from app.core.stages.base import StageContext
from app.core.stages.factory import build_pipeline
from app.core.stages.s6_guardrails import final_guardrails_check


def test_custom_stage_cannot_break_protected_zones() -> None:
    policy = PolicyConfig(
        enabled_stages=[
            "s1_normalize",
            "s2_segment",
            "custom_example",
            "s6_guardrails",
            "s7_assemble",
        ],
        max_edits_per_sentence=1,
        max_edits_total=5,
        max_changed_char_ratio=0.02,
        min_confidence_per_edit=0.99,
        min_confidence_overall=0.99,
        allow_punct_stage=False,
        language_gate_thresholds=0.9,
        pz_buffer_chars=2,
    )
    document = TextDocument(raw_text="Ссылка: https://example.com", working_text="Ссылка: https://example.com")
    document.working_text, document.placeholders_map, document.protected_spans = mask_protected_zones(
        document.working_text
    )
    context = StageContext(
        document=document,
        policy=policy,
        correlation_id="test",
        metrics=Metrics(),
    )

    for stage in build_pipeline(policy):
        stage.run(context)

    final_guardrails_check(context)
    assert context.document.working_text == "Ссылка: https://example.com"
