"""Targeted deterministic coverage tests for narrow single-token package P3."""
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


def test_single_token_typo_package_p3_positive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "single_token_p3.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="single-token-p3-positive")

    assert orchestrator.clean("решили делему быстро", mode="smart") == "решили дилемму быстро"
    assert orchestrator.clean("мне охото спать", mode="smart") == "мне охота спать"
    assert orchestrator.clean("без отделного входа", mode="smart") == "без отдельного входа"
    assert orchestrator.clean("список замечательнх мест", mode="smart") == "список замечательных мест"
    assert orchestrator.clean("проверили конкурентнсть цены", mode="smart") == "проверили конкурентность цены"


def test_single_token_typo_package_p3_protected_and_wrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "single_token_p3.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="single-token-p3-safety")

    assert orchestrator.clean("ссылка https://example.com/делему", mode="smart") == "ссылка https://example.com/делему"
    assert orchestrator.clean("тег #делему", mode="smart") == "тег #делему"
    assert orchestrator.clean("упоминание @делему", mode="smart") == "упоминание @делему"
    assert orchestrator.clean("скобки (делему)", mode="smart") == "скобки (делему)"
