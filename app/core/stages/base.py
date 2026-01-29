"""Интерфейсы стадий и контекст."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.model import TextDocument
from app.core.observability import Metrics
from app.core.policy import PolicyConfig


@dataclass
class StageContext:
    """Контекст, передаваемый между стадиями."""

    document: TextDocument
    policy: PolicyConfig
    correlation_id: str
    metrics: Metrics


class Stage(Protocol):
    """Интерфейс класса стадии."""

    name: str

    def run(self, context: StageContext) -> None:
        """Выполняет стадию."""
