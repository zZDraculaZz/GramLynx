"""Stage S7: assemble final output."""
from __future__ import annotations

import re

from app.core.protected_zones.detector import restore_protected_zones
from app.core.stages.base import StageContext


def assemble_text(context: StageContext) -> None:
    """Restore protected zones and finalize whitespace."""

    text = restore_protected_zones(
        context.document.working_text, context.document.placeholders_map
    )
    text = re.sub(r"\s+", " ", text).strip()
    context.document.working_text = text
