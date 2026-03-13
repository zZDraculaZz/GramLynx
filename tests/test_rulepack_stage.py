"""Tests for RulePack deterministic application in S3/S5."""
from __future__ import annotations

import pytest

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
import app.core.stages.helpers.deterministic_spelling as deterministic_spelling


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
    непревильно: неправильно
  typo_map_smart_ru: {}
  typo_map_strict:
    непревильно: неправильно
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
    assert result == "Это неправильно"


def test_rulepack_typo_map_respects_pz_buffer(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict: {}
  typo_map_smart_ru:
    непревильно: неправильно
  typo_map_smart:
    непревильно: неправильно
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    # token is outside PZ and deterministic typo_map replacement should apply
    text = "https://example.com непревильно"
    result = Orchestrator(correlation_id="t").clean(text, mode="smart")
    assert result == "https://example.com неправильно"


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
    непревильно: неправильно
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    text = "непревильно непревильно-бренд непревильно123 Непревильно"
    result = Orchestrator(correlation_id="t").clean(text, mode="smart")
    assert result == "неправильно непревильно-бренд непревильно123 Непревильно"


def test_stats_counters_present(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict_ru: {}
  typo_map_smart_ru:
    непревильно: неправильно
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
    assert result == "это неправильно, слово"
    assert orchestrator.last_run_stats["normalize_changes_count"] >= 1
    assert orchestrator.last_run_stats["typo_corrections_count"] >= 1
    assert orchestrator.last_run_stats["punctuation_fixes_count"] >= 1


class _FakeParse:
    def __init__(self, is_known: bool, score: float) -> None:
        self.is_known = is_known
        self.score = score


class _FakeMorphAnalyzer:
    def __init__(self, mapping: dict[str, list[_FakeParse]]) -> None:
        self._mapping = mapping

    def parse(self, token: str) -> list[_FakeParse]:
        return self._mapping.get(token, [_FakeParse(False, 0.0)])


def test_rulepack_morph_safety_allows_candidate(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
policies:
  smart:
    max_changed_char_ratio: 1.0
rulepack:
  enable_morph_safety_ru: true
  typo_map_smart_ru:
    абажаю: обожаю
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()
    deterministic_spelling._get_morph_analyzer.cache_clear()
    monkeypatch.setattr(
        deterministic_spelling,
        "_get_morph_analyzer",
        lambda: _FakeMorphAnalyzer(
            {
                "абажаю": [_FakeParse(False, 0.05)],
                "обожаю": [_FakeParse(True, 0.8)],
            }
        ),
    )

    orchestrator = Orchestrator(correlation_id="t")
    result = orchestrator.clean("я абажаю python", mode="smart")
    assert result == "я обожаю python"
    assert orchestrator.last_run_stats["morph_allowed_count"] == 1
    assert orchestrator.last_run_stats["morph_blocked_count"] == 0


def test_rulepack_morph_safety_blocks_when_source_normal(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
policies:
  smart:
    max_changed_char_ratio: 1.0
rulepack:
  enable_morph_safety_ru: true
  typo_map_smart_ru:
    миры: мирры
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()
    deterministic_spelling._get_morph_analyzer.cache_clear()
    monkeypatch.setattr(
        deterministic_spelling,
        "_get_morph_analyzer",
        lambda: _FakeMorphAnalyzer(
            {
                "миры": [_FakeParse(True, 0.95)],
                "мирры": [_FakeParse(False, 0.01)],
            }
        ),
    )

    orchestrator = Orchestrator(correlation_id="t")
    result = orchestrator.clean("миры", mode="smart")
    assert result == "миры"
    assert orchestrator.last_run_stats["morph_blocked_count"] == 1


def test_rulepack_morph_safety_keeps_pz_buffer(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  enable_morph_safety_ru: true
  typo_map_smart_ru:
    непревильно: неправильно
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()
    deterministic_spelling._get_morph_analyzer.cache_clear()
    monkeypatch.setattr(
        deterministic_spelling,
        "_get_morph_analyzer",
        lambda: _FakeMorphAnalyzer(
            {
                "непревильно": [_FakeParse(False, 0.05)],
                "неправильно": [_FakeParse(True, 0.9)],
            }
        ),
    )

    text = "https://example.com непревильно"
    result = Orchestrator(correlation_id="t").clean(text, mode="smart")
    assert result == "https://example.com неправильно"


def test_rulepack_morph_safety_is_deterministic(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
policies:
  smart:
    max_changed_char_ratio: 1.0
rulepack:
  enable_morph_safety_ru: true
  typo_map_smart_ru:
    абажаю: обожаю
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()
    deterministic_spelling._get_morph_analyzer.cache_clear()
    monkeypatch.setattr(
        deterministic_spelling,
        "_get_morph_analyzer",
        lambda: _FakeMorphAnalyzer(
            {
                "абажаю": [_FakeParse(False, 0.05)],
                "обожаю": [_FakeParse(True, 0.8)],
            }
        ),
    )

    orchestrator = Orchestrator(correlation_id="t")
    first = orchestrator.clean("я абажаю", mode="smart")
    second = orchestrator.clean("я абажаю", mode="smart")
    assert first == second == "я обожаю"


def test_rulepack_morph_unavailable_keeps_legacy_behavior(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
policies:
  smart:
    max_changed_char_ratio: 1.0
rulepack:
  enable_morph_safety_ru: true
  typo_map_smart_ru:
    абажаю: обожаю
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()
    deterministic_spelling._get_morph_analyzer.cache_clear()
    monkeypatch.setattr(deterministic_spelling, "_get_morph_analyzer", lambda: None)

    orchestrator = Orchestrator(correlation_id="t")
    result = orchestrator.clean("я абажаю", mode="smart")
    assert result == "я обожаю"
    assert orchestrator.last_run_stats["morph_allowed_count"] == 0


def test_rulepack_no_touch_exact_token_blocks_replacement(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_smart_ru:
    ваще: вообще
  no_touch_smart_ru:
    - ваще
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    result = Orchestrator(correlation_id="t").clean("ваще нормально", mode="smart")
    assert result == "ваще нормально"


def test_rulepack_no_touch_prefix_blocks_replacement(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_smart_ru:
    непревильно: неправильно
  no_touch_prefixes_ru:
    - "@"
    - "#"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    reset_app_config_cache()

    result = Orchestrator(correlation_id="t").clean("@непревильно #непревильно непревильно", mode="smart")
    assert result == "@непревильно #непревильно неправильно"
