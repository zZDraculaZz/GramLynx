"""Offline RU benchmark harness (RuSpellGold-style) for candidate-generation modes.

Runs benchmark cases in five modes:
- baseline: candidate generation disabled
- rapidfuzz_shadow: rapidfuzz enabled, shadow (no apply)
- rapidfuzz_apply: rapidfuzz enabled and applied
- symspell_shadow: symspell enabled, shadow (no apply)
- symspell_apply: symspell enabled and applied

Outputs only aggregated numeric stats.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator


DEFAULT_EVAL_DICTIONARY_SOURCE = "app/resources/ru_dictionary_v4.txt"


@dataclass(frozen=True)
class BenchmarkCase:
    input_text: str
    expected_clean_text: str


DEFAULT_BENCHMARK_PATH = Path(__file__).resolve().parent / "cases" / "ruspellgold_benchmark.jsonl"

# Deterministic dictionary for benchmark-mode candidate evaluation.
EVAL_DICTIONARY_WORDS: tuple[str, ...] = (
    "сегодня",
    "по-русски",
    "по-прежнему",
    "комментарий",
    "программа",
    "аккуратно",
    "коридор",
    "покупатель",
    "тишина",
    "кот",
    "кит",
    "сон",
    "сыр",
    "мир",
    "токен",
    "токан",
)


def _resolve_eval_dictionary_source() -> str:
    source = os.environ.get("GRAMLYNX_EVAL_DICTIONARY_SOURCE_RU", "").strip()
    if source:
        return source
    return DEFAULT_EVAL_DICTIONARY_SOURCE


def _runtime_config(candidate_enabled: bool, shadow_mode: bool, backend: str, dictionary_source: str) -> str:
    return f"""
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  enable_candidate_generation_ru: {str(candidate_enabled).lower()}
  candidate_shadow_mode_ru: {str(shadow_mode).lower()}
  candidate_backend: {backend}
  max_candidates_ru: 3
  max_edit_distance_ru: 1
  dictionary_source_ru: {dictionary_source}
  typo_min_token_len: 2
  typo_map_smart_ru: {{}}
  no_touch_prefixes_ru:
    - "@"
    - "#"
"""


def _load_benchmark_cases() -> tuple[BenchmarkCase, ...]:
    source = os.environ.get("GRAMLYNX_RUSPELLGOLD_PATH", "").strip()
    path = Path(source) if source else DEFAULT_BENCHMARK_PATH
    if not path.exists():
        raise FileNotFoundError(f"benchmark dataset not found: {path}")

    cases: list[BenchmarkCase] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = line.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid benchmark row at line {index}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"invalid benchmark row type at line {index}")

        input_text = payload.get("input_text")
        expected_clean_text = payload.get("expected_clean_text")
        if not isinstance(input_text, str) or not isinstance(expected_clean_text, str):
            raise ValueError(f"invalid benchmark schema at line {index}")
        if not input_text:
            raise ValueError(f"empty input_text at line {index}")

        cases.append(BenchmarkCase(input_text=input_text, expected_clean_text=expected_clean_text))

    if not cases:
        raise ValueError("benchmark dataset is empty")
    return tuple(cases)


def _ensure_backend_available(backend: str) -> None:
    if backend == "rapidfuzz" and importlib.util.find_spec("rapidfuzz") is None:
        raise RuntimeError("candidate backend unavailable: rapidfuzz is not installed")
    if backend == "symspell" and importlib.util.find_spec("symspellpy") is None:
        raise RuntimeError("candidate backend unavailable: symspellpy is not installed")


def evaluate_mode(mode_label: str) -> dict[str, float | int]:
    if mode_label == "baseline":
        candidate_enabled = False
        shadow_mode = False
        backend = "none"
    elif mode_label == "rapidfuzz_shadow":
        candidate_enabled = True
        shadow_mode = True
        backend = "rapidfuzz"
    elif mode_label == "rapidfuzz_apply":
        candidate_enabled = True
        shadow_mode = False
        backend = "rapidfuzz"
    elif mode_label == "symspell_shadow":
        candidate_enabled = True
        shadow_mode = True
        backend = "symspell"
    elif mode_label == "symspell_apply":
        candidate_enabled = True
        shadow_mode = False
        backend = "symspell"
    else:
        raise ValueError(f"unknown mode_label: {mode_label}")

    _ensure_backend_available(backend)

    benchmark_cases = _load_benchmark_cases()

    dictionary_source = _resolve_eval_dictionary_source()

    cfg_path = Path(tempfile.gettempdir()) / f"gramlynx_ruspellgold_eval_{mode_label}.yml"
    cfg_path.write_text(
        _runtime_config(candidate_enabled, shadow_mode, backend, dictionary_source),
        encoding="utf-8",
    )

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg_path)
    reset_app_config_cache()

    try:
        candidate_generated_total = 0
        candidate_applied_total = 0
        candidate_rejected_total = 0
        candidate_ambiguous_total = 0
        candidate_rejected_no_result_total = 0
        candidate_rejected_unsafe_candidate_total = 0
        candidate_rejected_morph_blocked_total = 0
        candidate_rejected_morph_unknown_total = 0
        candidate_ambiguous_tie_total = 0
        candidate_shadow_skipped_total = 0
        rollback_total = 0
        exact_match_pass_count = 0

        for index, case in enumerate(benchmark_cases):
            orchestrator = Orchestrator(correlation_id=f"ruspellgold-eval-{mode_label}-{index}")
            with contextlib.redirect_stdout(io.StringIO()):
                clean_text = orchestrator.clean(case.input_text, mode="smart")
            stats = orchestrator.last_run_stats

            candidate_generated_total += int(stats.get("candidate_generated_count", 0))
            candidate_applied_total += int(stats.get("candidate_applied_count", 0))
            candidate_rejected_total += int(stats.get("candidate_rejected_count", 0))
            candidate_ambiguous_total += int(stats.get("candidate_ambiguous_count", 0))
            candidate_rejected_no_result_total += int(stats.get("candidate_rejected_no_result_count", 0))
            candidate_rejected_unsafe_candidate_total += int(stats.get("candidate_rejected_unsafe_candidate_count", 0))
            candidate_rejected_morph_blocked_total += int(stats.get("candidate_rejected_morph_blocked_count", 0))
            candidate_rejected_morph_unknown_total += int(stats.get("candidate_rejected_morph_unknown_count", 0))
            candidate_ambiguous_tie_total += int(stats.get("candidate_ambiguous_tie_count", 0))
            candidate_shadow_skipped_total += int(stats.get("candidate_shadow_skipped_count", 0))
            rollback_total += int(bool(stats.get("rollback_applied", False)))
            exact_match_pass_count += int(clean_text == case.expected_clean_text)

        total_cases = len(benchmark_cases)
        exact_match_pass_rate = (exact_match_pass_count / total_cases) if total_cases else 0.0

        return {
            "total_cases": total_cases,
            "exact_match_pass_count": exact_match_pass_count,
            "exact_match_pass_rate": round(exact_match_pass_rate, 6),
            "candidate_generated_total": candidate_generated_total,
            "candidate_applied_total": candidate_applied_total,
            "candidate_rejected_total": candidate_rejected_total,
            "candidate_rejected_no_result_total": candidate_rejected_no_result_total,
            "candidate_rejected_unsafe_candidate_total": candidate_rejected_unsafe_candidate_total,
            "candidate_rejected_morph_blocked_total": candidate_rejected_morph_blocked_total,
            "candidate_rejected_morph_unknown_total": candidate_rejected_morph_unknown_total,
            "candidate_ambiguous_total": candidate_ambiguous_total,
            "candidate_ambiguous_tie_total": candidate_ambiguous_tie_total,
            "candidate_shadow_skipped_total": candidate_shadow_skipped_total,
            "rollback_total": rollback_total,
        }
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()


def evaluate_all_modes() -> dict[str, dict[str, float | int]]:
    return {
        "baseline": evaluate_mode("baseline"),
        "rapidfuzz_shadow": evaluate_mode("rapidfuzz_shadow"),
        "rapidfuzz_apply": evaluate_mode("rapidfuzz_apply"),
        "symspell_shadow": evaluate_mode("symspell_shadow"),
        "symspell_apply": evaluate_mode("symspell_apply"),
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_all_modes(), ensure_ascii=False, sort_keys=True))
