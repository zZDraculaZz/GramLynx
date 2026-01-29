"""Параметризованные тесты пайплайна по YAML-кейсам."""
from __future__ import annotations

import pytest

from app.core.orchestrator import Orchestrator
from tests.conftest import load_cases


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_pipeline_cases(case: dict) -> None:
    orchestrator = Orchestrator(correlation_id="cases")
    result = orchestrator.clean(case["input_text"], mode=case["mode"])
    assert result == case["expected_clean_text"]
