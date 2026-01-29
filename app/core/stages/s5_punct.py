"""Этап S5: пунктуация и оформление."""
from __future__ import annotations

import re

from app.core.stages.base import StageContext


def punct_corrections(context: StageContext) -> None:
    """Безопасная коррекция пробелов вокруг знаков пунктуации."""

    text = context.document.working_text
    text = re.sub(r"[ \t\f\v]+([,!?;:.])", r"\1", text)
    text = re.sub(r"([,!?;:.])(?=[^\s\n,!?;:.])", r"\1 ", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    context.document.working_text = text.strip(" \t")
