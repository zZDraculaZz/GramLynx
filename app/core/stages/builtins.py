"""Встроенные стадии пайплайна."""
from __future__ import annotations

from app.core.stages.base import Stage, StageContext
from app.core.stages.registry import register_stage
from app.core.stages.s1_normalize import normalize_text
from app.core.stages.s2_segment import segment_text
from app.core.stages.s3_spelling import spelling_corrections
from app.core.stages.s4_grammar import grammar_corrections
from app.core.stages.s5_punct import punct_corrections
from app.core.stages.s6_guardrails import guardrails_check
from app.core.stages.s7_assemble import assemble_text


@register_stage("s1_normalize")
class S1NormalizeStage:
    """Этап S1: безопасная нормализация."""

    name = "s1_normalize"

    def run(self, context: StageContext) -> None:
        normalize_text(context)


@register_stage("s2_segment")
class S2SegmentStage:
    """Этап S2: сегментация."""

    name = "s2_segment"

    def run(self, context: StageContext) -> None:
        segment_text(context)


@register_stage("s3_spelling")
class S3SpellingStage:
    """Этап S3: орфография."""

    name = "s3_spelling"

    def run(self, context: StageContext) -> None:
        spelling_corrections(context)


@register_stage("s4_grammar")
class S4GrammarStage:
    """Этап S4: грамматика."""

    name = "s4_grammar"

    def run(self, context: StageContext) -> None:
        grammar_corrections(context)


@register_stage("s5_punct")
class S5PunctStage:
    """Этап S5: пунктуация."""

    name = "s5_punct"

    def run(self, context: StageContext) -> None:
        punct_corrections(context)


@register_stage("s6_guardrails")
class S6GuardrailsStage:
    """Этап S6: guardrails."""

    name = "s6_guardrails"

    def run(self, context: StageContext) -> None:
        guardrails_check(context)


@register_stage("s7_assemble")
class S7AssembleStage:
    """Этап S7: сборка результата."""

    name = "s7_assemble"

    def run(self, context: StageContext) -> None:
        assemble_text(context)
