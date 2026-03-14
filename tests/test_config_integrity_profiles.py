"""Integrity checks for shipped YAML rollout profiles."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core import config as config_module
from app.core.config import load_app_config, reset_app_config_cache


@pytest.fixture(autouse=True)
def _reset_config_cache_between_tests() -> None:
    reset_app_config_cache()
    yield
    reset_app_config_cache()


def _load_yaml(path: str) -> dict[str, object]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_shipped_rollout_profile_set_is_expected() -> None:
    shipped = {p.name for p in Path(".").glob("config.smart_baseline*.yml")}
    assert shipped == {
        "config.smart_baseline_staging.yml",
        "config.smart_baseline_shadow_staging.yml",
    }


def test_config_example_safe_default_stays_off_and_loads(monkeypatch) -> None:
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(Path("config.example.yml").resolve()))
    reset_app_config_cache()

    cfg = load_app_config()
    assert cfg.rulepack.enable_candidate_generation_ru is False
    assert cfg.rulepack.candidate_shadow_mode_ru is False
    assert cfg.rulepack.candidate_backend == "symspell"
    assert cfg.rulepack.dictionary_source_ru == "app/resources/ru_dictionary_v7.txt"
    assert cfg.rulepack.max_candidates_ru == 3
    assert cfg.rulepack.max_edit_distance_ru == 1


def test_smart_baseline_staging_profile_integrity(monkeypatch) -> None:
    profile = _load_yaml("config.smart_baseline_staging.yml")
    rulepack = profile["rulepack"]
    assert rulepack["enable_candidate_generation_ru"] is True
    assert rulepack["candidate_shadow_mode_ru"] is False
    assert rulepack["candidate_backend"] == "symspell"
    assert rulepack["dictionary_source_ru"] == "app/resources/ru_dictionary_v7.txt"
    assert rulepack["max_candidates_ru"] == 3
    assert rulepack["max_edit_distance_ru"] == 1

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(Path("config.smart_baseline_staging.yml").resolve()))
    monkeypatch.setattr(config_module.importlib.util, "find_spec", lambda name: object() if name == "symspellpy" else None)
    reset_app_config_cache()

    cfg = load_app_config()
    assert cfg.rulepack.enable_candidate_generation_ru is True
    assert cfg.rulepack.candidate_shadow_mode_ru is False


def test_smart_baseline_shadow_profile_integrity(monkeypatch) -> None:
    profile = _load_yaml("config.smart_baseline_shadow_staging.yml")
    rulepack = profile["rulepack"]
    assert rulepack["enable_candidate_generation_ru"] is True
    assert rulepack["candidate_shadow_mode_ru"] is True
    assert rulepack["candidate_backend"] == "symspell"
    assert rulepack["dictionary_source_ru"] == "app/resources/ru_dictionary_v7.txt"
    assert rulepack["max_candidates_ru"] == 3
    assert rulepack["max_edit_distance_ru"] == 1

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(Path("config.smart_baseline_shadow_staging.yml").resolve()))
    monkeypatch.setattr(config_module.importlib.util, "find_spec", lambda name: object() if name == "symspellpy" else None)
    reset_app_config_cache()

    cfg = load_app_config()
    assert cfg.rulepack.enable_candidate_generation_ru is True
    assert cfg.rulepack.candidate_shadow_mode_ru is True
