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
    rapidfuzz_shadow = evaluate_mode("rapidfuzz_shadow")
    rapidfuzz_apply = evaluate_mode("rapidfuzz_apply")
    symspell_shadow = evaluate_mode("symspell_shadow")
    symspell_apply = evaluate_mode("symspell_apply")

    assert baseline["total_cases"] == len(FIXED_RU_CASES)
    assert rapidfuzz_shadow["total_cases"] == len(FIXED_RU_CASES)
    assert rapidfuzz_apply["total_cases"] == len(FIXED_RU_CASES)
    assert symspell_shadow["total_cases"] == len(FIXED_RU_CASES)
    assert symspell_apply["total_cases"] == len(FIXED_RU_CASES)

    # Shadow must remain output-equivalent to baseline.
    assert rapidfuzz_shadow["candidate_applied_total"] == 0
    assert rapidfuzz_shadow["candidate_shadow_skipped_total"] == rapidfuzz_shadow["candidate_generated_total"]
    assert rapidfuzz_shadow["exact_match_pass_count"] == baseline["exact_match_pass_count"]

    assert symspell_shadow["candidate_applied_total"] == 0
    assert symspell_shadow["candidate_shadow_skipped_total"] == symspell_shadow["candidate_generated_total"]
    assert symspell_shadow["exact_match_pass_count"] == baseline["exact_match_pass_count"]

    # Apply must stay safety-consistent.
    assert rapidfuzz_apply["rollback_total"] == 0
    assert symspell_apply["rollback_total"] == 0
    assert rapidfuzz_apply["candidate_rejected_unsafe_candidate_total"] == 0
    assert symspell_apply["candidate_rejected_unsafe_candidate_total"] == 0


def test_candidate_eval_aggregates_have_expected_shape() -> None:
    aggregates = evaluate_all_modes()

    for mode_name in (
        "baseline",
        "rapidfuzz_shadow",
        "rapidfuzz_apply",
        "symspell_shadow",
        "symspell_apply",
    ):
        mode_stats = aggregates[mode_name]
        assert set(mode_stats.keys()) == {
            "total_cases",
            "candidate_generated_total",
            "candidate_applied_total",
            "candidate_rejected_total",
            "candidate_ambiguous_total",
            "candidate_rejected_no_result_total",
            "candidate_rejected_unsafe_candidate_total",
            "candidate_rejected_morph_blocked_total",
            "candidate_rejected_morph_unknown_total",
            "candidate_ambiguous_tie_total",
            "candidate_shadow_skipped_total",
            "rollback_total",
            "exact_match_pass_count",
            "exact_match_pass_rate",
        }
        assert 0 <= float(mode_stats["exact_match_pass_rate"]) <= 1.0
        assert int(mode_stats["candidate_rejected_total"]) == (
            int(mode_stats["candidate_rejected_no_result_total"])
            + int(mode_stats["candidate_rejected_unsafe_candidate_total"])
            + int(mode_stats["candidate_rejected_morph_blocked_total"])
            + int(mode_stats["candidate_rejected_morph_unknown_total"])
        )
        assert int(mode_stats["candidate_ambiguous_total"]) == int(mode_stats["candidate_ambiguous_tie_total"])

    # defensive check: harness keeps outputs placeholder-safe via orchestrator guardrails
    assert PLACEHOLDER_TEMPLATE.split("{index}")[0] not in str(aggregates)


def test_candidate_eval_reason_buckets_are_informative_for_backend_comparison() -> None:
    rapidfuzz_apply = evaluate_mode("rapidfuzz_apply")
    symspell_apply = evaluate_mode("symspell_apply")

    # Expanded corpus must keep informative reason buckets when candidates are available.
    assert rapidfuzz_apply["candidate_rejected_total"] > 0
    assert symspell_apply["candidate_rejected_total"] > 0

    # no_result remains meaningful and non-zero in both backends.
    assert rapidfuzz_apply["candidate_rejected_no_result_total"] > 0
    assert symspell_apply["candidate_rejected_no_result_total"] > 0

    # If optional backends are installed, expanded corpus should expose backend differences.
    if rapidfuzz_apply["candidate_generated_total"] > 0 and symspell_apply["candidate_generated_total"] > 0:
        assert rapidfuzz_apply["candidate_ambiguous_total"] >= 1
        assert symspell_apply["candidate_applied_total"] >= 1
        assert (
            rapidfuzz_apply["candidate_ambiguous_total"] != symspell_apply["candidate_ambiguous_total"]
            or rapidfuzz_apply["candidate_applied_total"] != symspell_apply["candidate_applied_total"]
            or rapidfuzz_apply["exact_match_pass_count"] != symspell_apply["exact_match_pass_count"]
        )
