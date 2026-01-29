"""Тесты детерминированных орфографических замен."""
from __future__ import annotations

from app.core.orchestrator import Orchestrator


def test_spelling_deterministic_applied_in_smart() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Жыраф и шыба гуляют в парке"
    result = orchestrator.clean(text, mode="smart")
    assert result == "Жираф и шиба гуляют в парке"


def test_spelling_deterministic_not_in_strict() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Жыраф и шыба гуляют в парке"
    result = orchestrator.clean(text, mode="strict")
    assert result == text


def test_spelling_deterministic_outside_protected_zone() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Жыть https://example.com/жы"
    result = orchestrator.clean(text, mode="smart")
    assert result == "Жить https://example.com/жы"


def test_spelling_deterministic_not_in_code_block() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Вот код:\n```python\nжы\n```"
    result = orchestrator.clean(text, mode="smart")
    assert result == text


def test_spelling_deterministic_keeps_email_unchanged() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Почта: user+test@mail.example"
    result = orchestrator.clean(text, mode="smart")
    assert result == text
