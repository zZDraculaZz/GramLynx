"""Этап S6: guardrails и откат."""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from app.core.protected_zones.detector import (
    count_placeholders,
    mask_protected_zones,
    placeholders_intact,
    restore_protected_zones,
)
from app.core.prom_metrics import observe_rollback
from app.core.stages.base import StageContext




def _policy_mode(context: StageContext) -> str:
    """Infer mode label from active policy."""

    return "smart" if context.policy.allow_punct_stage else "strict"


def guardrails_check(context: StageContext) -> None:
    """Проверяет инварианты и выполняет откат при нарушении."""

    document = context.document
    baseline = document.safe_snapshot_text or document.raw_text
    baseline_len = max(len(baseline), 1)
    changed_ratio = _changed_ratio(baseline, document.working_text, baseline_len)
    ratio_ok = changed_ratio <= context.policy.max_changed_char_ratio
    edits_ok = len(document.audit_log.applied_edits) <= context.policy.max_edits_total
    placeholders_ok = placeholders_intact(document.working_text, document.placeholders_map)

    if not placeholders_ok or not ratio_ok or not edits_ok:
        _rollback_to_snapshot(context)
        observe_rollback(mode=_policy_mode(context))
        if not placeholders_ok:
            document.audit_log.rollbacks.append("placeholders_missing")
        if not ratio_ok:
            document.audit_log.rollbacks.append("changed_ratio_exceeded")
        if not edits_ok:
            document.audit_log.rollbacks.append("edits_limit_exceeded")


def final_guardrails_check(context: StageContext) -> None:
    """Финальная проверка после сборки результата."""

    document = context.document
    text = document.working_text
    no_placeholders = count_placeholders(text) == 0
    originals_ok = _placeholders_restored(text, document.placeholders_map)
    detector_ok = _detector_consistent(text, document.placeholders_map)

    if not no_placeholders or not originals_ok or not detector_ok:
        _rollback_to_snapshot(context)
        observe_rollback(mode=_policy_mode(context))
        if not no_placeholders:
            document.audit_log.rollbacks.append("placeholders_left")
        if not originals_ok:
            document.audit_log.rollbacks.append("protected_mismatch")
        if not detector_ok:
            document.audit_log.rollbacks.append("protected_detector_mismatch")


def _rollback_to_snapshot(context: StageContext) -> None:
    """Возвращает документ в безопасное состояние."""

    document = context.document
    snapshot_text = document.safe_snapshot_text or document.raw_text
    snapshot_placeholders = (
        document.safe_snapshot_placeholders or document.placeholders_map
    )
    document.placeholders_map = dict(snapshot_placeholders)
    document.working_text = restore_protected_zones(snapshot_text, snapshot_placeholders)


def _changed_ratio(baseline: str, current: str, baseline_len: int) -> float:
    """Считает долю изменений с учётом разницы длины."""

    matcher = SequenceMatcher(None, baseline, current)
    return 1.0 - matcher.ratio()


def _placeholders_restored(text: str, placeholders: dict[str, str]) -> bool:
    """Проверяет, что все исходные фрагменты присутствуют byte-to-byte."""

    working = text
    for placeholder, original in placeholders.items():
        if original not in working:
            return False
        working = working.replace(original, placeholder, 1)
    return True


def _detector_consistent(text: str, placeholders: dict[str, str]) -> bool:
    """Перепроверяет, что детектор видит исходные защищённые фрагменты."""

    _, detected_placeholders, _ = mask_protected_zones(text)
    detected = Counter(detected_placeholders.values())
    expected = Counter(placeholders.values())
    return detected >= expected
