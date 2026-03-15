"""Targeted deterministic coverage tests for follow-up narrow single-token package."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _reset_config_cache_between_tests() -> None:
    reset_app_config_cache()
    yield
    reset_app_config_cache()


def _write_runtime_cfg(path: Path) -> None:
    path.write_text(
        """
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  enable_candidate_generation_ru: true
  candidate_shadow_mode_ru: false
  candidate_backend: symspell
  max_candidates_ru: 3
  max_edit_distance_ru: 1
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
  typo_map_smart_ru: {}
  no_touch_prefixes_ru:
    - "@"
    - "#"
""",
        encoding="utf-8",
    )


def test_single_token_typo_followup_positive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "single_token_followup.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="single-token-followup-positive")

    assert orchestrator.clean("с интерентом давно", mode="smart") == "с интернетом давно"
    assert orchestrator.clean("а если наоброт", mode="smart") == "а если наоборот"
    assert orchestrator.clean("сумашедший ритм", mode="smart") == "сумасшедший ритм"
    assert orchestrator.clean("мне необходмо время", mode="smart") == "мне необходимо время"
    assert orchestrator.clean("работает благодвря людям", mode="smart") == "работает благодаря людям"


def test_single_token_typo_followup_protected_and_wrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "single_token_followup.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="single-token-followup-safety")

    assert orchestrator.clean("ссылка https://example.com/наоброт", mode="smart") == "ссылка https://example.com/наоброт"
    assert orchestrator.clean("тег #наоброт", mode="smart") == "тег #наоброт"
    assert orchestrator.clean("упоминание @наоброт", mode="smart") == "упоминание @наоброт"
    assert orchestrator.clean("скобки (наоброт)", mode="smart") == "скобки (наоброт)"
