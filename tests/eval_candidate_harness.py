"""Offline evaluation harness for RU candidate-generation modes.

Runs fixed cases in three modes:
- baseline: candidate generation disabled
- shadow: candidate generation enabled, shadow (no apply)
- apply: candidate generation enabled and applied

Outputs only aggregated numeric stats.
"""
from __future__ import annotations

import contextlib
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


@dataclass(frozen=True)
class EvalCase:
    input_text: str
    expected_clean_text: str


FIXED_RU_CASES: tuple[EvalCase, ...] = (
    EvalCase("севодня будет встреча", "сегодня будет встреча"),
    EvalCase("порусски пишу", "по-русски пишу"),
    EvalCase("попрежнему жду", "по-прежнему жду"),
    EvalCase("https://example.com севодня", "https://example.com сегодня"),
    EvalCase("@севодня", "@севодня"),
    EvalCase("(севодня)", "(севодня)"),
    EvalCase("севодня123", "севодня123"),
)


def _runtime_config(candidate_enabled: bool, shadow_mode: bool) -> str:
    return f"""
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  enable_candidate_generation_ru: {str(candidate_enabled).lower()}
  candidate_shadow_mode_ru: {str(shadow_mode).lower()}
  candidate_backend: rapidfuzz
  max_candidates_ru: 3
  max_edit_distance_ru: 1
  dictionary_source_ru: app/resources/ru_dictionary_v1.txt
  typo_map_smart_ru: {{}}
  no_touch_prefixes_ru:
    - "@"
"""


def evaluate_mode(mode_label: str) -> dict[str, float | int]:
    if mode_label == "baseline":
        candidate_enabled = False
        shadow_mode = False
    elif mode_label == "shadow":
        candidate_enabled = True
        shadow_mode = True
    elif mode_label == "apply":
        candidate_enabled = True
        shadow_mode = False
    else:
        raise ValueError(f"unknown mode_label: {mode_label}")

    cfg_path = Path(tempfile.gettempdir()) / f"gramlynx_candidate_eval_{mode_label}.yml"
    cfg_path.write_text(_runtime_config(candidate_enabled, shadow_mode), encoding="utf-8")

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg_path)
    reset_app_config_cache()

    try:
        candidate_generated_total = 0
        candidate_applied_total = 0
        candidate_rejected_total = 0
        candidate_ambiguous_total = 0
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
        "shadow": evaluate_mode("shadow"),
        "apply": evaluate_mode("apply"),
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_all_modes(), ensure_ascii=False, sort_keys=True))
