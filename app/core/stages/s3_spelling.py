"""Этап S3: консервативные орфографические исправления."""
from __future__ import annotations

import re

from app.core.config import load_app_config
from app.core.model import Edit
from app.core.observability import log_event
from app.core.prom_metrics import observe_corrections_applied
from app.core.protected_zones.lexicon import get_allowlist, get_denylist
from app.core.stages.base import StageContext
from app.core.stages.helpers.deterministic_spelling import (
    find_replacements,
    find_rulepack_replacements,
)

STAGE_NAME = "s3_spelling"


def spelling_corrections(context: StageContext) -> None:
    """Применяет только детерминированные замены вне Protected Zones."""

    text = context.document.working_text
    cfg = load_app_config().rulepack
    mode = _mode_label(context)
    typo_map = cfg.typo_map_for_mode(mode)

    edits = find_rulepack_replacements(
        text=text,
        typo_map=typo_map,
        min_token_len=cfg.typo_min_token_len,
        allowlist=get_allowlist(),
        denylist=get_denylist(),
        no_touch_tokens=cfg.no_touch_for_mode(mode),
        no_touch_prefixes=cfg.no_touch_prefixes_for_mode(mode),
        enable_morph_safety_ru=cfg.enable_morph_safety_ru,
    )
    context.document.morph_blocked_count += edits.morph_stats.morph_blocked_count
    context.document.morph_allowed_count += edits.morph_stats.morph_allowed_count
    context.document.morph_unknown_count += edits.morph_stats.morph_unknown_count
    edits_list = edits.edits

    # backward compatibility for built-in deterministic fixes when no YAML map configured
    if not edits_list and not typo_map:
        edits_list = find_replacements(text)

    if not edits_list:
        return

    offset = 0
    last_end = -1
    applied_count = 0
    for edit in edits_list:
        if edit.start < last_end:
            continue
        current_start = edit.start + offset
        current_end = edit.end + offset
        if not _edit_allowed(context, current_start, current_end):
            context.document.audit_log.rejected_edits.append(
                Edit(
                    start=current_start,
                    end=current_end,
                    before=edit.before,
                    after=edit.after,
                    edit_type="spelling",
                    confidence=1.0,
                    stage=STAGE_NAME,
                    safe_reason="blocked_near_protected_zone",
                )
            )
            continue
        text = text[:current_start] + edit.after + text[current_end:]
        offset += len(edit.after) - len(edit.before)
        last_end = edit.end
        applied_count += 1
        context.document.audit_log.applied_edits.append(
            Edit(
                start=current_start,
                end=current_end,
                before=edit.before,
                after=edit.after,
                edit_type="spelling",
                confidence=1.0,
                stage=STAGE_NAME,
                safe_reason="deterministic_replacement",
            )
        )
    context.document.working_text = text

    if applied_count > 0:
        context.document.typo_corrections_count += applied_count
        context.metrics.edits_applied_total[(mode, STAGE_NAME)] = (
            context.metrics.edits_applied_total.get((mode, STAGE_NAME), 0) + applied_count
        )
        observe_corrections_applied(mode=mode, stage=STAGE_NAME, count=applied_count)
        log_event(
            event="stage_corrections_applied",
            correlation_id=context.correlation_id,
            mode=mode,
            stage=STAGE_NAME,
            corrections_applied=applied_count,
        )


def _mode_label(context: StageContext) -> str:
    return "smart" if context.policy.allow_punct_stage else "strict"


def _edit_allowed(context: StageContext, start: int, end: int) -> bool:
    """Проверяет, что правка не попадает в Protected Zones и буфер вокруг них."""

    buffer_chars = context.policy.pz_buffer_chars
    for span_start, span_end in _placeholder_spans(context.document.working_text):
        if start < span_end + buffer_chars and end > span_start - buffer_chars:
            return False
    return True


def _placeholder_spans(text: str) -> list[tuple[int, int]]:
    """Возвращает спаны плейсхолдеров Protected Zones."""

    spans = []
    for match in re.finditer(r"⟦PZ\d+⟧", text):
        spans.append((match.start(), match.end()))
    return spans
