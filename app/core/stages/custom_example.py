"""Пример кастомной стадии (отключена по умолчанию)."""
from __future__ import annotations

from app.core.stages.base import StageContext
from app.core.stages.registry import register_stage


@register_stage("custom_example")
class CustomExampleStage:
    """Пример кастомной стадии: попытка модификации текста."""

    name = "custom_example"

    def run(self, context: StageContext) -> None:
        # Имитация небезопасной правки: нарушаем плейсхолдеры.
        context.document.working_text = context.document.working_text.replace(
            "⟦PZ0⟧", "BROKEN"
        )
