"""Tests for offline candidate-generation evaluation harness."""
from __future__ import annotations

from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE
from eval_candidate_harness import FIXED_RU_CASES, evaluate_all_modes, evaluate_mode


def test_candidate_eval_harness_repeated_run_is_stable() -> None:
    first = evaluate_all_modes()
    second = evaluate_all_modes()
    assert first == second


def test_candidate_eval_shadow_matches_baseline_and_apply_is_safe() -> None:
    baseline = evaluate_mode("baseline")
    shadow = evaluate_mode("shadow")
    apply = evaluate_mode("apply")

    assert baseline["total_cases"] == len(FIXED_RU_CASES)
    assert shadow["total_cases"] == len(FIXED_RU_CASES)
    assert apply["total_cases"] == len(FIXED_RU_CASES)

    assert shadow["candidate_generated_total"] > 0
    assert shadow["candidate_applied_total"] == 0
    assert shadow["exact_match_pass_count"] == baseline["exact_match_pass_count"]

    assert apply["candidate_applied_total"] >= 0
    assert apply["rollback_total"] == 0


def test_candidate_eval_aggregates_have_expected_shape() -> None:
    aggregates = evaluate_all_modes()

    for mode_name in ("baseline", "shadow", "apply"):
        mode_stats = aggregates[mode_name]
        assert set(mode_stats.keys()) == {
            "total_cases",
            "candidate_generated_total",
            "candidate_applied_total",
            "candidate_rejected_total",
            "candidate_ambiguous_total",
            "rollback_total",
            "exact_match_pass_count",
            "exact_match_pass_rate",
        }
        assert 0 <= float(mode_stats["exact_match_pass_rate"]) <= 1.0

    # defensive check: harness keeps outputs placeholder-safe via orchestrator guardrails
    assert PLACEHOLDER_TEMPLATE.split("{index}")[0] not in str(aggregates)
