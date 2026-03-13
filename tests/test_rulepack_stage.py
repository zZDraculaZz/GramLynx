"""Tests for RulePack deterministic application in S3/S5."""
from __future__ import annotations

import pytest

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _reset_config_cache_between_tests() -> None:
    reset_app_config_cache()
    yield
    reset_app_config_cache()


def test_rulepack_typo_map_applies_in_strict(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
policies:
  strict:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  typo_map_strict_ru:
    непревильно: правильно
  typo_map_smart_ru: {}
  typo_map_strict:
    непревильно: правильно
  typo_map_smart: {}
  punctuation:
    fix_space_before: true
    fix_space_after: true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    result = Orchestrator(correlation_id="t").clean("Это непревильно", mode="strict")
    assert result == "Это правильно"


def test_rulepack_typo_map_respects_pz_buffer(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict: {}
  typo_map_smart_ru:
    непревильно: правильно
  typo_map_smart:
    непревильно: правильно
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    # token is adjacent to PZ and should remain unchanged by safe checks
    text = "https://example.com непревильно"
    result = Orchestrator(correlation_id="t").clean(text, mode="smart")
    assert result == text


def test_rulepack_punctuation_toggle(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict: {}
  typo_map_smart: {}
  punctuation_spacing_ru:
    fix_space_before: false
    fix_space_after: false
  punctuation:
    fix_space_before: false
    fix_space_after: false
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    text = "Привет ,мир"
    result = Orchestrator(correlation_id="t").clean(text, mode="smart")
    assert result == text


def test_rulepack_ru_skips_hyphenated_mixed_and_name_like(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict_ru: {}
  typo_map_smart_ru:
    непревильно: правильно
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    text = "непревильно непревильно-бренд непревильно123 Непревильно"
    result = Orchestrator(correlation_id="t").clean(text, mode="smart")
    assert result == "правильно непревильно-бренд непревильно123 Непревильно"


def test_stats_counters_present(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict_ru: {}
  typo_map_smart_ru:
    непревильно: правильно
  safe_normalize:
    collapse_spaces: true
    trim_line_edges: true
    collapse_blank_lines: true
  punctuation_spacing_ru:
    fix_space_before: true
    fix_space_after: true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    orchestrator = Orchestrator(correlation_id="t")
    result = orchestrator.clean("  это непревильно ,слово  ", mode="smart")
    assert result == "это непревильно ,слово"
    assert orchestrator.last_run_stats["normalize_changes_count"] >= 1
    assert orchestrator.last_run_stats["typo_corrections_count"] >= 1
    assert orchestrator.last_run_stats["punctuation_fixes_count"] >= 1
