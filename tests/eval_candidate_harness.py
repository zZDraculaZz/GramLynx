"""Offline evaluation harness for RU candidate-generation modes.

Runs fixed cases in five modes:
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


DEFAULT_EVAL_DICTIONARY_SOURCE = "app/resources/ru_dictionary_v7.txt"


@dataclass(frozen=True)
class EvalCase:
    input_text: str
    expected_clean_text: str


FIXED_RU_CASES: tuple[EvalCase, ...] = (
    # baseline typo-map-covered edits
    EvalCase("севодня будет встреча", "сегодня будет встреча"),
    EvalCase("порусски пишу", "по-русски пишу"),
    EvalCase("попрежнему жду", "по-прежнему жду"),
    # harder single-token / candidate-only edits (5-10 chars)
    EvalCase("тишена", "тишина"),
    EvalCase("калидор", "коридор"),
    EvalCase("коментарий", "комментарий"),
    EvalCase("програма", "программа"),
    EvalCase("однокласник", "одноклассник"),
    EvalCase("акуратно", "аккуратно"),
    EvalCase("пакупатель", "покупатель"),
    EvalCase("превычка", "привычка"),
    # shorter harder tokens (candidate-only)
    EvalCase("кат", "кот"),
    EvalCase("сн", "сон"),
    EvalCase("кид", "кит"),
    EvalCase("сор", "сыр"),
    EvalCase("котт", "кот"),
    EvalCase("мирр", "мир"),
    # candidate-only ambiguity / near-tie
    EvalCase("токин", "токин"),
    EvalCase("карп", "карп"),
    # noisy misspellings on edit-distance boundary
    EvalCase("кар", "кар"),
    EvalCase("кордор", "кордор"),
    EvalCase("комментрий", "комментрий"),
    # morph-sensitive but safe candidate-only block
    EvalCase("миры", "миры"),
    EvalCase("мирры", "мирры"),
    EvalCase("коты", "коты"),
    # candidate path should be rejected by wrappers / no-touch / safety
    EvalCase("@кат", "@кат"),
    EvalCase("#кат", "#кат"),
    EvalCase("(кат)", "(кат)"),
    EvalCase('"кат"', '"кат"'),
    EvalCase("/кат/", "/кат/"),
    EvalCase("token:кат", "token:кат"),
    EvalCase("кат_ключ", "кат_ключ"),
    EvalCase("кaт", "кaт"),
    EvalCase("кат123", "кат123"),
    EvalCase("КаТ", "КаТ"),
    EvalCase("кот2", "кот2"),
    # protected-zone classes (including near-PZ-like adjacency)
    EvalCase("https://example.com кат", "https://example.com кот"),
    EvalCase("кат https://example.com", "кот https://example.com"),
    EvalCase("катhttps://example.com", "катhttps://example.com"),
    EvalCase("(https://example.com):кат", "(https://example.com):кат"),
    EvalCase("mail user@mail.example кат", "mail user@mail.example кот"),
    EvalCase("кат 550e8400-e29b-41d4-a716-446655440000", "кот 550e8400-e29b-41d4-a716-446655440000"),
)


# Deliberately ordered to make symspell frequency ranking differ from rapidfuzz tie handling.
EVAL_DICTIONARY_WORDS: tuple[str, ...] = (
    "тишина",
    "коридор",
    "комментарий",
    "программа",
    "одноклассник",
    "аккуратно",
    "покупатель",
    "привычка",
    "кот",
    "коты",
    "кит",
    "сыр",
    "мир",
    "миры",
    "сон",
    "код",
    "токен",
    "токан",
    "карп",
    "кар",
    "карта",
    "соня",
    "сани",
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
"""


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

    dictionary_source = _resolve_eval_dictionary_source()

    cfg_path = Path(tempfile.gettempdir()) / f"gramlynx_candidate_eval_{mode_label}.yml"
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

        for index, case in enumerate(FIXED_RU_CASES):
            orchestrator = Orchestrator(correlation_id=f"candidate-eval-{mode_label}-{index}")
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

        total_cases = len(FIXED_RU_CASES)
        exact_match_pass_rate = (exact_match_pass_count / total_cases) if total_cases else 0.0

        return {
            "total_cases": total_cases,
            "candidate_generated_total": candidate_generated_total,
            "candidate_applied_total": candidate_applied_total,
            "candidate_rejected_total": candidate_rejected_total,
            "candidate_ambiguous_total": candidate_ambiguous_total,
            "candidate_rejected_no_result_total": candidate_rejected_no_result_total,
            "candidate_rejected_unsafe_candidate_total": candidate_rejected_unsafe_candidate_total,
            "candidate_rejected_morph_blocked_total": candidate_rejected_morph_blocked_total,
            "candidate_rejected_morph_unknown_total": candidate_rejected_morph_unknown_total,
            "candidate_ambiguous_tie_total": candidate_ambiguous_tie_total,
            "candidate_shadow_skipped_total": candidate_shadow_skipped_total,
            "rollback_total": rollback_total,
            "exact_match_pass_count": exact_match_pass_count,
            "exact_match_pass_rate": round(exact_match_pass_rate, 6),
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
