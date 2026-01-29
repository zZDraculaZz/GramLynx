"""Этап S7: сборка финального результата."""
from __future__ import annotations

import re

from app.core.protected_zones.detector import restore_protected_zones
from app.core.stages.base import StageContext


def assemble_text(context: StageContext) -> None:
    """Восстанавливает Protected Zones и финализирует пробелы."""

    text = restore_protected_zones(
        context.document.working_text, context.document.placeholders_map
    )
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
