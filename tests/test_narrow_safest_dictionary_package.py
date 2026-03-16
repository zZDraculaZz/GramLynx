"""Targeted checks for ultra-narrow safest dictionary coverage package."""
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


def test_narrow_safest_dictionary_package_positive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "narrow_safest_dictionary.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="narrow-safest-dictionary-positive")

    assert orchestrator.clean("Все биохимические процессы происходят благодяря воде.", mode="smart") == "Все биохимические процессы происходят благодаря воде."
    assert orchestrator.clean("Вике необходимол время", mode="smart") == "Вике необходимо время"
    assert orchestrator.clean("У вас могут быть препядствия", mode="smart") == "У вас могут быть препятствия"
    assert orchestrator.clean("Наблюдение в соответсвии с пожеланиями", mode="smart") == "Наблюдение в соответствии с пожеланиями"
    assert orchestrator.clean("без обьяснения причин", mode="smart") == "без объяснения причин"


def test_narrow_safest_dictionary_package_protected_and_wrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "narrow_safest_dictionary.yml"
    _write_runtime_cfg(cfg)
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="narrow-safest-dictionary-safety")

    assert orchestrator.clean("ссылка https://example.com/соответсвии", mode="smart") == "ссылка https://example.com/соответсвии"
    assert orchestrator.clean("тег #соответсвии", mode="smart") == "тег #соответсвии"
    assert orchestrator.clean("упоминание @соответсвии", mode="smart") == "упоминание @соответсвии"
    assert orchestrator.clean("скобки (соответсвии)", mode="smart") == "скобки (соответсвии)"
