"""Safety/fuzz tests for RulePack v2 without external fuzz dependencies."""
from __future__ import annotations

import os
import random
import tempfile
from pathlib import Path

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE


def _random_ru_word(rng: random.Random, min_len: int = 5, max_len: int = 10) -> str:
    alphabet = "абвгдежзийклмнопрстуфхцчшщьыъэюя"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(min_len, max_len)))


def _protected_fragment(seed: int) -> str:
    variants = [
        f"https://example{seed}.com/path/{seed}",
        f"user{seed}@mail{seed}.example",
        f"550e8400-e29b-41d4-a716-{seed % 1_000_000_000_000:012d}",
        f"{seed}",
    ]
    return variants[seed % len(variants)]


def test_rulepack_v2_safety_fuzz_seeded() -> None:
    cfg = Path(tempfile.gettempdir()) / "gramlynx_rulepack_v2_fuzz.yml"
    cfg.write_text(
        """
policies:
  smart:
    max_changed_char_ratio: 1.0
rulepack:
  typo_map_strict_ru:
    непревильно: неправильно
    севодня: сегодня
    сегодя: сегодня
    пачему: почему
    пожалуста: пожалуйста
    извените: извините
  typo_map_smart_ru:
    непревильно: неправильно
    абажаю: обожаю
    севодня: сегодня
    сегодя: сегодня
    пачему: почему
    пожалуста: пожалуйста
    извените: извините
    превет: привет
    спосибо: спасибо
    кагда: когда
    жызнь: жизнь
    слишкам: слишком
    ваще: вообще
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

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg)
    reset_app_config_cache()

    try:
        rng = random.Random(271828)
        for i in range(120):
            pz = _protected_fragment(i + 1)
            typo = ["непревильно", "абажаю", "севодня", "пожалуста", "сегодя", "пачему"][i % 6]
            safe_word = _random_ru_word(rng)
            nick_like = f"user_{safe_word}"
            at_nick = f"@{safe_word}"
            user_name = f"{safe_word}_name"
            hash_tag = f"#{safe_word}"
            brand_like = f"iPhone{(i % 9) + 1}"
            mixed_script = f"{safe_word[:3]}t3st"
            mixed_digit = f"{safe_word[:3]}123"
            slang_token = "ваще"
            near_pz_glued = f"{pz}{typo}"
            near_pz_punct = f"({pz}),{typo}"
            near_pz_colon = f"({pz}):{typo}"
            near_pz_semicolon = f"({pz});{typo}"
            wrapped_round = f"({typo})"
            wrapped_quote = f"\"{typo}\""
            wrapped_path = f"/{typo}/"
            wrapped_colon = f"key:{typo}"
            wrapped_underscore = f"key_{typo}"
            text = (
                f"  начало {typo}  {safe_word}-бренд {typo}123 Непревильно "
                f"{nick_like} {at_nick} {user_name} {hash_tag} {brand_like} {mixed_script} {mixed_digit} {slang_token} {near_pz_glued} "
                f"{near_pz_punct} {near_pz_colon} {near_pz_semicolon} {wrapped_round} {wrapped_quote} {wrapped_path} {wrapped_colon} {wrapped_underscore} слово ,слово  конец  "
            )

            first = Orchestrator(correlation_id=f"v2-fuzz-{i}").clean(text, mode="smart")
            second = Orchestrator(correlation_id=f"v2-fuzz-repeat-{i}").clean(text, mode="smart")

            # deterministic behavior
            assert first == second
            result = first

            # protected fragment must survive byte-to-byte
            assert pz in result
            # placeholder markers must never leak
            assert PLACEHOLDER_TEMPLATE.split("{index}")[0] not in result

            # first standalone typo token is either safely corrected or left unchanged by guardrails
            first_token_after_prefix = result.split()[1]
            expected_after = {
                "непревильно": "неправильно",
                "абажаю": "обожаю",
                "севодня": "сегодня",
                "пожалуста": "пожалуйста",
                "сегодя": "сегодня",
                "пачему": "почему",
            }[typo]
            assert first_token_after_prefix in {typo, expected_after}

            # no-touch token categories must remain untouched
            assert f"{safe_word}-бренд" in result
            assert f"{typo}123" in result
            assert "Непревильно" in result
            assert nick_like in result
            assert at_nick in result
            assert user_name in result
            assert hash_tag in result
            assert brand_like in result
            assert mixed_script in result
            assert mixed_digit in result
            assert " ваще " in f" {result} "
            assert wrapped_round in result
            assert wrapped_quote in result
            assert wrapped_path in result
            assert wrapped_colon in result
            assert wrapped_underscore in result

            # near-PZ cases stay safe: glued form must remain no-touch, punctuated forms must keep PZ intact
            assert f"({pz})," in result
            assert f"({pz}):" in result
            assert f"({pz});" in result
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()
