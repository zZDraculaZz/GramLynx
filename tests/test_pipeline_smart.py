"""Pipeline smart tests."""
from __future__ import annotations

from app.core.orchestrator import Orchestrator


def test_smart_pipeline_preserves_pz() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    result = orchestrator.run("Ссылка https://example.com   тут", mode="smart")
    assert result == "Ссылка https://example.com тут"
