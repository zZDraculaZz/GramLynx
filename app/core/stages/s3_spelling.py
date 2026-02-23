"""Этап S3: консервативные орфографические исправления."""
from __future__ import annotations

import re

from app.core.config import load_app_config
from app.core.model import Edit
from app.core.protected_zones.lexicon import get_allowlist, get_denylist
from app.core.stages.base import StageContext
from app.core.stages.helpers.deterministic_spelling import (
    find_replacements,
    find_rulepack_replacements,
)


def spelling_corrections(context: StageContext) -> None:
    """Применяет только детерминированные замены вне Protected Zones."""

    text = context.document.working_text
    cfg = load_app_config().rulepack
    typo_map = cfg.typo_map_smart if context.policy.allow_punct_stage else cfg.typo_map_strict

    edits = find_rulepack_replacements(
        text=text,
        typo_map=typo_map,
        min_token_len=cfg.typo_min_token_len,
        allowlist=get_allowlist(),
        denylist=get_denylist(),
    )

    # backward compatibility for built-in deterministic fixes when no YAML map configured
    if not edits and not typo_map:
        edits = find_replacements(text)

    if not edits:
        return

    offset = 0
    last_end = -1
    for edit in edits:
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
                    stage="s3_spelling",
                    safe_reason="blocked_near_protected_zone",
                )
            )
            continue
        text = text[:current_start] + edit.after + text[current_end:]
        offset += len(edit.after) - len(edit.before)
        last_end = edit.end
        context.document.audit_log.applied_edits.append(
            Edit(
                start=current_start,
                end=current_end,
                before=edit.before,
                after=edit.after,
                edit_type="spelling",
                confidence=1.0,
                stage="s3_spelling",
                safe_reason="deterministic_replacement",
            )
        )
    context.document.working_text = text


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
