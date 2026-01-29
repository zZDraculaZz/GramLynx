"""Stage interfaces and context."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.model import TextDocument
from app.core.observability import Metrics
from app.core.policy import PolicyConfig


@dataclass
class StageContext:
    """Context passed through stages."""

    document: TextDocument
    policy: PolicyConfig
    correlation_id: str
    metrics: Metrics
