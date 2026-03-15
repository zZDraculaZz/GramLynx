"""Targeted deterministic coverage tests for extra narrow single-token package."""
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


def test_single_token_typo_extra_package_positive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "single_token_extra.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="single-token-extra-positive")

    assert orchestrator.clean("параметр не соответсвует норме", mode="smart") == "параметр не соответствует норме"
    assert orchestrator.clean("это дейстительно важно", mode="smart") == "это действительно важно"
    assert orchestrator.clean("по колличеству мест", mode="smart") == "по количеству мест"
    assert orchestrator.clean("старый компьтер шумит", mode="smart") == "старый компьютер шумит"
    assert orchestrator.clean("паступят", mode="smart") == "поступят"


def test_single_token_typo_extra_package_protected_and_wrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "single_token_extra.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="single-token-extra-safety")

    assert orchestrator.clean("ссылка https://example.com/соответсвует", mode="smart") == "ссылка https://example.com/соответсвует"
    assert orchestrator.clean("тег #соответсвует", mode="smart") == "тег #соответсвует"
    assert orchestrator.clean("упоминание @соответсвует", mode="smart") == "упоминание @соответсвует"
    assert orchestrator.clean("скобки (соответсвует)", mode="smart") == "скобки (соответсвует)"
