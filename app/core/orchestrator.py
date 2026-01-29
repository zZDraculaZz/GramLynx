"""Оркестратор пайплайна."""
from __future__ import annotations

import time
from typing import Dict, List

from app.core.confidence import aggregate_confidence
from app.core.model import TextDocument
from app.core.observability import Metrics, log_event
from app.core.policy import get_policy
from app.core.protected_zones.detector import mask_protected_zones
from app.core.stages.base import StageContext
from app.core.stages.s1_normalize import normalize_text
from app.core.stages.s2_segment import segment_text
from app.core.stages.s3_spelling import spelling_corrections
from app.core.stages.s4_grammar import grammar_corrections
from app.core.stages.s5_punct import punct_corrections
from app.core.stages.s6_guardrails import final_guardrails_check, guardrails_check
from app.core.stages.s7_assemble import assemble_text


class Orchestrator:
    """Запускает и контролирует пайплайн очистки."""

    def __init__(self, correlation_id: str) -> None:
        self.correlation_id = correlation_id
        self.metrics = Metrics()

    def run(self, text: str, mode: str) -> str:
        policy = get_policy(mode)
        document = TextDocument(raw_text=text, working_text=text)
        context = StageContext(
            document=document,
            policy=policy,
            correlation_id=self.correlation_id,
            metrics=self.metrics,
        )
        self.metrics.requests_total[mode] = self.metrics.requests_total.get(mode, 0) + 1

        stages: Dict[str, callable] = {
            "s1_normalize": normalize_text,
            "s2_segment": segment_text,
            "s3_spelling": spelling_corrections,
            "s4_grammar": grammar_corrections,
            "s5_punct": punct_corrections,
            "s6_guardrails": guardrails_check,
            "s7_assemble": assemble_text,
        }

        start_time = time.time()
        document.working_text, document.placeholders_map, document.protected_spans = (
            mask_protected_zones(document.working_text)
        )
        document.safe_snapshot_placeholders = dict(document.placeholders_map)
        document.safe_snapshot_spans = list(document.protected_spans)
        document.safe_snapshot_text = document.working_text

        for stage_name in policy.enabled_stages:
            stage = stages[stage_name]
            stage_start = time.time()
            stage(context)
            duration_ms = (time.time() - stage_start) * 1000
            self.metrics.stage_duration_ms[(stage_name, mode)] = duration_ms
            log_event(
                event="stage_completed",
                correlation_id=self.correlation_id,
                mode=mode,
                stage=stage_name,
                duration_ms=duration_ms,
            )

        final_guardrails_check(context)
        document.confidence = aggregate_confidence(document)
        total_ms = (time.time() - start_time) * 1000
        log_event(
            event="request_completed",
            correlation_id=self.correlation_id,
            mode=mode,
            duration_ms=total_ms,
        )
        return document.working_text

    def clean(self, text: str, mode: str) -> str:
        """Публичный метод для запуска очистки текста."""

        return self.run(text=text, mode=mode)
