"""Tests for offline candidate-generation evaluation harness."""
from __future__ import annotations

import importlib.util

import pytest

import eval_candidate_harness as candidate_harness
from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE
from eval_candidate_harness import FIXED_RU_CASES, evaluate_all_modes, evaluate_mode


RAPIDFUZZ_AVAILABLE = importlib.util.find_spec("rapidfuzz") is not None
SYMSPELL_AVAILABLE = importlib.util.find_spec("symspellpy") is not None
ALL_BACKENDS_AVAILABLE = RAPIDFUZZ_AVAILABLE and SYMSPELL_AVAILABLE


def test_candidate_eval_harness_repeated_run_is_stable() -> None:
    if not ALL_BACKENDS_AVAILABLE:
        first = evaluate_mode("baseline")
        second = evaluate_mode("baseline")
        assert first == second
        with pytest.raises(RuntimeError):
            evaluate_all_modes()
        return

    first = evaluate_all_modes()
    second = evaluate_all_modes()
    assert first == second


def test_candidate_eval_shadow_matches_baseline_and_apply_is_safe() -> None:
    baseline = evaluate_mode("baseline")
    assert baseline["total_cases"] == len(FIXED_RU_CASES)

    if not ALL_BACKENDS_AVAILABLE:
        with pytest.raises(RuntimeError):
            evaluate_mode("rapidfuzz_shadow")
        with pytest.raises(RuntimeError):
            evaluate_mode("rapidfuzz_apply")
        with pytest.raises(RuntimeError):
            evaluate_mode("symspell_shadow")
        with pytest.raises(RuntimeError):
            evaluate_mode("symspell_apply")
        return

    rapidfuzz_shadow = evaluate_mode("rapidfuzz_shadow")
    rapidfuzz_apply = evaluate_mode("rapidfuzz_apply")
    symspell_shadow = evaluate_mode("symspell_shadow")
    symspell_apply = evaluate_mode("symspell_apply")

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
    if not ALL_BACKENDS_AVAILABLE:
        baseline = evaluate_mode("baseline")
        assert set(baseline.keys()) == {
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
        return

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
    if not ALL_BACKENDS_AVAILABLE:
        with pytest.raises(RuntimeError):
            evaluate_mode("rapidfuzz_apply")
        with pytest.raises(RuntimeError):
            evaluate_mode("symspell_apply")
        return

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


def test_candidate_eval_fail_closed_when_rapidfuzz_missing(monkeypatch) -> None:
    monkeypatch.setattr(candidate_harness.importlib.util, "find_spec", lambda name: None if name == "rapidfuzz" else object())
    with pytest.raises(RuntimeError, match="rapidfuzz"):
        evaluate_mode("rapidfuzz_apply")


def test_candidate_eval_fail_closed_when_symspell_missing(monkeypatch) -> None:
    monkeypatch.setattr(candidate_harness.importlib.util, "find_spec", lambda name: None if name == "symspellpy" else object())
    with pytest.raises(RuntimeError, match="symspellpy"):
        evaluate_mode("symspell_apply")


def test_candidate_eval_baseline_still_works_without_backend_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(candidate_harness.importlib.util, "find_spec", lambda name: None)
    stats = evaluate_mode("baseline")
    assert int(stats["total_cases"]) == len(FIXED_RU_CASES)


def test_candidate_eval_symspell_v5_improves_over_v4_dictionary(monkeypatch) -> None:
    if not SYMSPELL_AVAILABLE:
        pytest.skip("symspellpy is not available")

    monkeypatch.setenv("GRAMLYNX_EVAL_DICTIONARY_SOURCE_RU", "app/resources/ru_dictionary_v4.txt")
    v4 = evaluate_mode("symspell_apply")

    monkeypatch.setenv("GRAMLYNX_EVAL_DICTIONARY_SOURCE_RU", "app/resources/ru_dictionary_v5.txt")
    v5 = evaluate_mode("symspell_apply")

    assert int(v5["candidate_rejected_no_result_total"]) <= int(v4["candidate_rejected_no_result_total"])
    assert float(v5["exact_match_pass_rate"]) >= float(v4["exact_match_pass_rate"])
    assert int(v5["rollback_total"]) == 0
    assert int(v5["candidate_rejected_unsafe_candidate_total"]) == 0
