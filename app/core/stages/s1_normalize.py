"""Этап S1: безопасная нормализация."""
from __future__ import annotations

import re
import unicodedata

from app.core.stages.base import StageContext


def normalize_text(context: StageContext) -> None:
    """Консервативная нормализация пробелов и Unicode с сохранением переводов строк."""

    text = unicodedata.normalize("NFKC", context.document.working_text)
    text = text.replace("\u200b", "")
    text = text.replace("\u00A0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines(keepends=True)
    normalized_lines = []
    for line in lines:
        if line.endswith("\n"):
            content = re.sub(r"[ \t\f\v]+", " ", line[:-1]).strip()
            normalized_lines.append(content + "\n")
        else:
            content = re.sub(r"[ \t\f\v]+", " ", line).strip()
            normalized_lines.append(content)
    context.document.working_text = "".join(normalized_lines)
    context.document.safe_snapshot_text = context.document.working_text
    context.document.safe_snapshot_placeholders = dict(context.document.placeholders_map)
    context.document.safe_snapshot_spans = list(context.document.protected_spans)
