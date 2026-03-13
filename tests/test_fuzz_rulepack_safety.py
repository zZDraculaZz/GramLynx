"""Fuzz safety tests for RulePack deterministic corrections."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE

TOKEN_RE = re.compile(r"\b[а-яё]+\b")


def _pz_snippet(seed: int) -> str:
    i = abs(seed)
    variants = [
        f"https://example{i}.com/path/{i}",
        f"user{i}@mail{i}.example",
        f"550e8400-e29b-41d4-a716-{i % 1_000_000_000_000:012d}",
        f"{i % 100000}",
    ]
    return variants[i % len(variants)]


def _build_text(target: str, pz: str) -> str:
    # first target is far from PZ and may be corrected, second is glued to PZ and must stay unchanged
    return f"начало {target} середина {pz}{target} конец"


@settings(max_examples=80, deadline=None)
@given(
    typo=st.sampled_from(["непревильно", "абажаю"]),
    seed=st.integers(min_value=1, max_value=10_000),
)
def test_fuzz_rulepack_safety(typo: str, seed: int) -> None:
    cfg = Path(tempfile.gettempdir()) / "gramlynx_rulepack_fuzz.yml"
    cfg.write_text(
        """
rulepack:
  typo_map_strict:
    непревильно: правильно
  typo_map_smart:
    непревильно: правильно
    абажаю: обожаю
  punctuation:
    fix_space_before: true
    fix_space_after: true
""",
        encoding="utf-8",
    )
    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg)
    reset_app_config_cache()

    pz = _pz_snippet(seed)
    text = _build_text(typo, pz)
    try:
        result = Orchestrator(correlation_id="fuzz-rulepack").clean(text, mode="smart")
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()

    # PZ must survive byte-to-byte.
    assert pz in result

    # Placeholder markers must never leak.
    placeholder_prefix = PLACEHOLDER_TEMPLATE.split("{index}")[0]
    assert placeholder_prefix not in result

    # Corrections only for allowed whole lowercase tokens.
    src_tokens = TOKEN_RE.findall(text)
    dst_tokens = TOKEN_RE.findall(result)
    assert len(src_tokens) == len(dst_tokens)

    allowed_in = {"непревильно", "абажаю"}
    allowed_out = {"правильно", "обожаю"}
    for before, after in zip(src_tokens, dst_tokens):
        if before != after:
            assert before in allowed_in
            assert after in allowed_out

    # Adjacent-to-PZ typo instance should remain unchanged due to token boundary constraints.
    assert f"{pz}{typo}" in result
