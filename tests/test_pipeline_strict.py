"""Pipeline strict tests."""
from __future__ import annotations

from app.core.orchestrator import Orchestrator


def test_strict_pipeline_normalizes_only() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    result = orchestrator.run("Текст   с  пробелами", mode="strict")
    assert result == "Текст с пробелами"
