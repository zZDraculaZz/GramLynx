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
rulepack:
  typo_map_strict_ru:
    непревильно: правильно
  typo_map_smart_ru:
    непревильно: правильно
    абажаю: обожаю
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
            typo = "непревильно" if i % 2 == 0 else "абажаю"
            safe_word = _random_ru_word(rng)
            text = (
                f"  начало {typo}  {safe_word}-бренд {typo}123 Непревильно "
                f"{pz}{typo} слово ,слово  конец  "
            )

            result = Orchestrator(correlation_id=f"v2-fuzz-{i}").clean(text, mode="smart")

            # protected fragment must survive byte-to-byte
            assert pz in result
            # placeholder markers must never leak
            assert PLACEHOLDER_TEMPLATE.split("{index}")[0] not in result
            # only standalone lowercase typo tokens are corrected
            if typo == "непревильно":
                assert "правильно" in result
            else:
                assert "обожаю" in result
            # no-touch token categories must remain untouched
            assert f"{safe_word}-бренд" in result
            assert f"{typo}123" in result
            assert "Непревильно" in result
            assert f"{pz}{typo}" in result
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()
