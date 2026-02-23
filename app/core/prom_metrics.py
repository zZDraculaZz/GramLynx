"""Optional Prometheus metrics for GramLynx."""
from __future__ import annotations

import os
from difflib import SequenceMatcher
from typing import Any

ROLLBACKS_TOTAL: Any = None
PZ_SPANS_TOTAL: Any = None
CHANGED_RATIO_HISTOGRAM: Any = None
CONFIDENCE_HISTOGRAM: Any = None


def _ensure_metrics() -> bool:
    """Initialize collectors lazily only when metrics are enabled."""

    global ROLLBACKS_TOTAL, PZ_SPANS_TOTAL, CHANGED_RATIO_HISTOGRAM, CONFIDENCE_HISTOGRAM

    if os.getenv("GRAMLYNX_ENABLE_METRICS") != "1":
        return False

    if ROLLBACKS_TOTAL is not None:
        return True

    from prometheus_client import Counter, Histogram

    ROLLBACKS_TOTAL = Counter(
        "gramlynx_rollbacks_total",
        "Total number of guardrails rollbacks.",
        labelnames=("mode",),
    )
    PZ_SPANS_TOTAL = Counter(
        "gramlynx_pz_spans_total",
        "Total number of detected protected-zone spans.",
        labelnames=("mode",),
    )
    CHANGED_RATIO_HISTOGRAM = Histogram(
        "gramlynx_changed_ratio_bucket",
        "Changed ratio distribution for processed documents.",
        buckets=(0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0),
    )
    CONFIDENCE_HISTOGRAM = Histogram(
        "gramlynx_confidence_bucket",
        "Document confidence distribution.",
        buckets=(0.0, 0.5, 0.7, 0.85, 0.9, 0.95, 0.99, 1.0),
    )
    return True


def observe_pz_spans(mode: str, count: int) -> None:
    """Observe number of protected-zone spans for a request."""

    if not _ensure_metrics():
        return
    if count > 0:
        PZ_SPANS_TOTAL.labels(mode=mode).inc(count)


def observe_rollback(mode: str) -> None:
    """Observe a guardrails rollback."""

    if not _ensure_metrics():
        return
    ROLLBACKS_TOTAL.labels(mode=mode).inc()


def observe_document_stats(mode: str, baseline: str, current: str, confidence: float | None) -> None:
    """Observe changed-ratio and confidence at the end of processing."""

    if not _ensure_metrics():
        return

    ratio = 1.0 - SequenceMatcher(None, baseline, current).ratio()
    ratio = min(max(ratio, 0.0), 1.0)
    CHANGED_RATIO_HISTOGRAM.observe(ratio)

    if confidence is not None:
        conf = min(max(confidence, 0.0), 1.0)
        CONFIDENCE_HISTOGRAM.observe(conf)
