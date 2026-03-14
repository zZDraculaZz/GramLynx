"""Tests for YAML-based application configuration."""
from __future__ import annotations

import importlib

import pytest

import app.core.config as config_module
from app.core.config import ConfigError, load_app_config, reset_app_config_cache
from app.core.policy import get_policy
from app.core.protected_zones.lexicon import get_allowlist, get_denylist


@pytest.fixture(autouse=True)
def _reset_config_cache_between_tests() -> None:
    reset_app_config_cache()
    yield
    reset_app_config_cache()


def _reset(monkeypatch) -> None:
    monkeypatch.delenv("GRAMLYNX_CONFIG_YAML", raising=False)
    reset_app_config_cache()


def test_valid_yaml_applies_overrides(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "valid.yml"
    config_file.write_text(
        """
limits:
  max_body_bytes: 2048
  max_text_chars: 123
policies:
  strict:
    max_changed_char_ratio: 0.03
    pz_buffer_chars: 5
    enabled_stages: [s1_normalize, s2_segment, s6_guardrails, s7_assemble]
lexicon:
  allowlist: [One, Two]
  denylist: [Bad]
rulepack:
  typo_map_strict_ru:
    непревильно: неправильно
  safe_normalize:
    collapse_spaces: true
    trim_line_edges: true
    collapse_blank_lines: false
  punctuation_spacing_ru:
    fix_space_before: false
    fix_space_after: true
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    reset_app_config_cache()

    import app.main as app_main

    importlib.reload(app_main)

    cfg = load_app_config()
    assert cfg.limits.max_body_bytes == 2048
    assert cfg.limits.max_text_chars == 123

    strict = get_policy("strict")
    assert strict.max_changed_char_ratio == 0.03
    assert strict.pz_buffer_chars == 5
    assert strict.enabled_stages == ["s1_normalize", "s2_segment", "s6_guardrails", "s7_assemble"]

    assert get_allowlist() == {"One", "Two"}
    assert get_denylist() == {"Bad"}
    assert cfg.rulepack.typo_map_for_mode("strict") == {"непревильно": "неправильно"}
    assert cfg.rulepack.safe_normalize.collapse_blank_lines is False
    assert cfg.rulepack.punctuation_for_mode().fix_space_before is False


def test_invalid_yaml_fails_closed_on_startup(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "invalid.yml"
    config_file.write_text(
        """
limits:
  max_body_bytes: LEAK_ME_VALUE
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    reset_app_config_cache()

    with pytest.raises(RuntimeError, match="Invalid config YAML") as exc_info:
        import app.main as app_main

        importlib.reload(app_main)

    assert "LEAK_ME_VALUE" not in str(exc_info.value)


def test_defaults_used_when_env_not_set(monkeypatch) -> None:
    _reset(monkeypatch)

    cfg = load_app_config()
    assert cfg.limits.max_body_bytes == 1_048_576
    assert cfg.limits.max_text_chars == 20_000

    strict = get_policy("strict")
    assert strict.max_changed_char_ratio == 0.02
    assert strict.pz_buffer_chars == 2

    # Global safe default stays fail-closed: candidate generation is off.
    assert cfg.rulepack.enable_candidate_generation_ru is False
    assert cfg.rulepack.candidate_backend == "none"

    assert get_allowlist() == {"Python", "FastAPI", "Docker"}
    assert get_denylist() == {"TODO", "FIXME"}


def test_candidate_backend_can_be_symspell_when_feature_enabled(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "candidate_backend_symspell.yml"
    config_file.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_backend: symspell
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    monkeypatch.setattr(config_module.importlib.util, "find_spec", lambda name: object() if name == "symspellpy" else None)
    reset_app_config_cache()

    cfg = load_app_config()
    assert cfg.rulepack.enable_candidate_generation_ru is True
    assert cfg.rulepack.candidate_backend == "symspell"


def test_recommended_symspell_v7_baseline_can_be_loaded_from_yaml(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "recommended_symspell_v7_baseline.yml"
    config_file.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_shadow_mode_ru: false
  candidate_backend: symspell
  max_candidates_ru: 3
  max_edit_distance_ru: 1
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    reset_app_config_cache()

    cfg = load_app_config()
    assert cfg.rulepack.enable_candidate_generation_ru is True
    assert cfg.rulepack.candidate_shadow_mode_ru is False
    assert cfg.rulepack.candidate_backend == "symspell"
    assert cfg.rulepack.max_candidates_ru == 3
    assert cfg.rulepack.max_edit_distance_ru == 1
    assert cfg.rulepack.dictionary_source_ru == "app/resources/ru_dictionary_v7.txt"


def test_shadow_first_symspell_v7_profile_can_be_loaded_from_yaml(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "shadow_first_symspell_v7_profile.yml"
    config_file.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_shadow_mode_ru: true
  candidate_backend: symspell
  max_candidates_ru: 3
  max_edit_distance_ru: 1
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    monkeypatch.setattr(config_module.importlib.util, "find_spec", lambda name: object() if name == "symspellpy" else None)
    reset_app_config_cache()

    cfg = load_app_config()
    assert cfg.rulepack.enable_candidate_generation_ru is True
    assert cfg.rulepack.candidate_shadow_mode_ru is True
    assert cfg.rulepack.candidate_backend == "symspell"
    assert cfg.rulepack.max_candidates_ru == 3
    assert cfg.rulepack.max_edit_distance_ru == 1
    assert cfg.rulepack.dictionary_source_ru == "app/resources/ru_dictionary_v7.txt"


def test_candidate_preflight_fail_closed_when_backend_dependency_missing(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "candidate_preflight_missing_backend.yml"
    config_file.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_backend: symspell
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    monkeypatch.setattr(config_module.importlib.util, "find_spec", lambda name: None)
    reset_app_config_cache()

    with pytest.raises(ConfigError, match="dependency missing"):
        load_app_config()


def test_candidate_preflight_fail_closed_when_dictionary_path_missing(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "candidate_preflight_missing_dict.yml"
    config_file.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_backend: symspell
  dictionary_source_ru: app/resources/not_existing_dictionary.txt
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    monkeypatch.setattr(config_module.importlib.util, "find_spec", lambda name: object())
    reset_app_config_cache()

    with pytest.raises(ConfigError, match="path not found"):
        load_app_config()


def test_candidate_preflight_fail_closed_when_backend_value_invalid(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "candidate_preflight_invalid_backend.yml"
    config_file.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_backend: unsupported_backend
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    reset_app_config_cache()

    with pytest.raises(ConfigError, match="candidate backend must be one of"):
        load_app_config()
