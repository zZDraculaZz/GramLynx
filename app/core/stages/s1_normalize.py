"""Stage S1: safe normalization."""
from __future__ import annotations

import re
import unicodedata

from app.core.stages.base import StageContext


def normalize_text(context: StageContext) -> None:
    """Apply conservative normalization to whitespace and Unicode."""

    text = unicodedata.normalize("NFKC", context.document.working_text)
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    context.document.working_text = text.strip()
