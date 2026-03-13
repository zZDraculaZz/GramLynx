"""Этап S1: безопасная нормализация."""
from __future__ import annotations

import re
import unicodedata

from app.core.config import load_app_config
from app.core.stages.base import StageContext


def normalize_text(context: StageContext) -> None:
    """Консервативная нормализация пробелов и Unicode с сохранением переводов строк."""

    before = context.document.working_text
    cfg = load_app_config().rulepack.safe_normalize

    text = unicodedata.normalize("NFKC", before)
    text = text.replace("\u200b", "")
    text = text.replace("\u00A0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines(keepends=True)
    normalized_lines = []
    for line in lines:
        line_content = line[:-1] if line.endswith("\n") else line
        if cfg.collapse_spaces:
            line_content = re.sub(r"[ \t\f\v]+", " ", line_content)
        if cfg.trim_line_edges:
            line_content = line_content.strip()
        if line.endswith("\n"):
            normalized_lines.append(line_content + "\n")
        else:
            normalized_lines.append(line_content)
    normalized_text = "".join(normalized_lines)
    if cfg.collapse_blank_lines:
        normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text)

    context.document.working_text = normalized_text
    context.document.normalize_changes_count += int(before != normalized_text)
    context.document.safe_snapshot_text = context.document.working_text
    context.document.safe_snapshot_placeholders = dict(context.document.placeholders_map)
    context.document.safe_snapshot_spans = list(context.document.protected_spans)
