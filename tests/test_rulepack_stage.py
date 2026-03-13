"""Tests for RulePack deterministic application in S3/S5."""
from __future__ import annotations

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator


def test_rulepack_typo_map_applies_in_strict(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
policies:
  strict:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
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
