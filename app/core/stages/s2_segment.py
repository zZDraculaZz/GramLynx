"""Stage S2: segmentation."""
from __future__ import annotations

import re

from app.core.model import Token
from app.core.stages.base import StageContext


def segment_text(context: StageContext) -> None:
    """Simple whitespace tokenization with offsets."""

    tokens = []
    for match in re.finditer(r"\S+", context.document.working_text):
        tokens.append(Token(text=match.group(0), start=match.start(), end=match.end()))
    context.document.tokens = tokens
