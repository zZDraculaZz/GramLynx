"""Этап S5: пунктуация и оформление."""
from __future__ import annotations

import re

from app.core.config import load_app_config
from app.core.model import Edit
from app.core.stages.base import StageContext


PUNCT_MARKS = r",\.:;!?"
LETTER_AFTER_PUNCT = r"[A-Za-zА-Яа-яЁё]"


def punct_corrections(context: StageContext) -> None:
    """Безопасная коррекция пробелов вокруг знаков пунктуации."""

    text = context.document.working_text
    edits = []
    punctuation_cfg = load_app_config().rulepack.punctuation

    if punctuation_cfg.fix_space_before:
        for match in re.finditer(rf"[ \t\f\v]+([{PUNCT_MARKS}])", text):
            before = match.group(0)
            after = match.group(1)
            edits.append((match.start(), match.end(), before, after))

    if punctuation_cfg.fix_space_after:
        for match in re.finditer(rf"([{PUNCT_MARKS}])(?={LETTER_AFTER_PUNCT})", text):
            before = match.group(1)
            after = f"{before} "
            edits.append((match.start(), match.end(), before, after))

    edits.sort(key=lambda item: item[0])
    offset = 0
    for start, end, before, after in edits:
        current_start = start + offset
        current_end = end + offset
        if not _edit_allowed(context, current_start, current_end):
            context.document.audit_log.rejected_edits.append(
                Edit(
                    start=current_start,
                    end=current_end,
                    before=before,
                    after=after,
                    edit_type="punct",
                    confidence=1.0,
                    stage="s5_punct",
                    safe_reason="blocked_near_protected_zone",
                )
            )
            continue
        text = text[:current_start] + after + text[current_end:]
        offset += len(after) - len(before)
        context.document.audit_log.applied_edits.append(
            Edit(
                start=current_start,
                end=current_end,
                before=before,
                after=after,
                edit_type="punct",
                confidence=1.0,
                stage="s5_punct",
                safe_reason="whitespace_punct",
            )
        )

    text = re.sub(r"[ \t\f\v]+", " ", text)
    context.document.working_text = text.strip(" \t")


def _edit_allowed(context: StageContext, start: int, end: int) -> bool:
    """Проверяет, что правка не задевает Protected Zones и буфер вокруг них."""

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
