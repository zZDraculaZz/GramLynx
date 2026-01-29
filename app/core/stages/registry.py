"""Реестр стадий пайплайна."""
from __future__ import annotations

from typing import Callable, Dict, Type

from app.core.stages.base import Stage

STAGE_REGISTRY: Dict[str, Type[Stage]] = {}


def register_stage(name: str) -> Callable[[Type[Stage]], Type[Stage]]:
    """Декоратор для регистрации стадии по имени."""

    def decorator(stage_cls: Type[Stage]) -> Type[Stage]:
        STAGE_REGISTRY[name] = stage_cls
        return stage_cls

    return decorator


def get_stage_class(name: str) -> Type[Stage]:
    """Возвращает класс стадии из реестра."""

    return STAGE_REGISTRY[name]
