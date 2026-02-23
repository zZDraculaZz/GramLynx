"""Оркестратор пайплайна."""
from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import List

from app.core.confidence import aggregate_confidence
from app.core.model import TextDocument
from app.core.observability import Metrics, log_event
from app.core.policy import get_policy
from app.core.prom_metrics import observe_document_stats, observe_pz_spans
from app.core.protected_zones.detector import mask_protected_zones
from app.core.stages.base import StageContext
from app.core.stages.factory import build_pipeline
from app.core.stages.s6_guardrails import final_guardrails_check


class Orchestrator:
    """Запускает и контролирует пайплайн очистки."""

    def __init__(self, correlation_id: str) -> None:
        self.correlation_id = correlation_id
        self.metrics = Metrics()
        self.last_run_stats: dict[str, object] = {}

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
        observe_pz_spans(mode=mode, count=len(document.protected_spans))

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
        observe_document_stats(
            mode=mode,
            baseline=document.raw_text,
            current=document.working_text,
            confidence=document.confidence,
        )
        changed_ratio = 1.0 - SequenceMatcher(None, document.raw_text, document.working_text).ratio()
        changed_ratio = min(max(changed_ratio, 0.0), 1.0)
        self.last_run_stats = {
            "input_len_chars": len(document.raw_text),
            "output_len_chars": len(document.working_text),
            "changed_ratio": round(changed_ratio, 6),
            "confidence": None if document.confidence is None else round(document.confidence, 6),
            "rollback_applied": bool(document.audit_log.rollbacks),
            "pz_spans_count": len(document.protected_spans),
        }

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
