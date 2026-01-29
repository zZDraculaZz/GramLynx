"""Проверки security hardening для guardrails."""
from __future__ import annotations

from app.core.orchestrator import Orchestrator


def test_punct_does_not_touch_url_adjacent_punct() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Ссылка: https://example.com,ok?"
    result = orchestrator.clean(text, mode="smart")
    assert result == text


def test_punct_does_not_touch_email_adjacent_punct() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Почта: admin@mail.example,ok?"
    result = orchestrator.clean(text, mode="smart")
    assert result == text


def test_punct_does_not_touch_url_with_parenthesis() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "Ссылка (https://example.com) ок"
    result = orchestrator.clean(text, mode="smart")
    assert result == text


def test_edit_budget_triggers_rollback() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "А,Б,В,Г,Д,Е,Ж,З,И,К,Л,М"
    result = orchestrator.clean(text, mode="smart")
    assert result == text


def test_changed_ratio_triggers_rollback() -> None:
    orchestrator = Orchestrator(correlation_id="test")
    text = "A,B,C,D,E"
    result = orchestrator.clean(text, mode="smart")
    assert result == text
