"""Оркестратор пайплайна."""
from __future__ import annotations

import time
from typing import List

from app.core.confidence import aggregate_confidence
from app.core.model import TextDocument
from app.core.observability import Metrics, log_event
from app.core.policy import get_policy
from app.core.protected_zones.detector import mask_protected_zones
from app.core.stages.base import StageContext
from app.core.stages.factory import build_pipeline
from app.core.stages.s6_guardrails import final_guardrails_check


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

        start_time = time.time()
        document.working_text, document.placeholders_map, document.protected_spans = (
            mask_protected_zones(document.working_text)
        )
        document.safe_snapshot_placeholders = dict(document.placeholders_map)
        document.safe_snapshot_spans = list(document.protected_spans)
        document.safe_snapshot_text = document.working_text

        for stage in build_pipeline(policy):
            stage_start = time.time()
            stage.run(context)
            duration_ms = (time.time() - stage_start) * 1000
            self.metrics.stage_duration_ms[(stage.name, mode)] = duration_ms
            log_event(
                event="stage_completed",
                correlation_id=self.correlation_id,
                mode=mode,
                stage=stage.name,
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
