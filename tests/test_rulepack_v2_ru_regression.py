"""Large RU regression suite for RulePack v2."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _reset_config_cache_between_tests() -> None:
    reset_app_config_cache()
    yield
    reset_app_config_cache()


def _load_cases() -> dict[str, list[dict[str, str]]]:
    data = yaml.safe_load(Path("tests/cases/rulepack_v2_ru_cases.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_rulepack_v2_ru_regression(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "rulepack_v2_ru_runtime.yml"
    cfg.write_text(
        """
policies:
  strict:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s4_grammar, s5_punct, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  typo_map_strict_ru:
    непревильно: неправильно
    севодня: сегодня
    сегодя: сегодня
    пачему: почему
    пожалуста: пожалуйста
    пажалуста: пожалуйста
    извените: извините
    сдесь: здесь
    кстате: кстати
  typo_map_smart_ru:
    непревильно: неправильно
    абажаю: обожаю
    севодня: сегодня
    сегодя: сегодня
    пачему: почему
    пожалуста: пожалуйста
    пажалуста: пожалуйста
    извените: извините
    извеняюсь: извиняюсь
    сдесь: здесь
    кстате: кстати
    превет: привет
    спосибо: спасибо
    кагда: когда
    жызнь: жизнь
    слишкам: слишком
    симпотичный: симпатичный
    агенство: агентство
    прийдти: прийти
  no_touch_strict_ru:
    - ща
    - ваще
    - имхо
  no_touch_smart_ru:
    - ща
    - ваще
    - имхо
    - сорян
    - кринж
  no_touch_prefixes_ru:
    - "@"
    - "#"
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

    cases = _load_cases()
    for mode, items in cases.items():
        assert mode in {"strict", "smart"}
        for case in items:
            result = Orchestrator(correlation_id=f"v2-{mode}").clean(case["input"], mode=mode)
            assert result == case["expected_clean_text"]
