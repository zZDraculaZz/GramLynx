"""Tests for offline RuSpellGold-style benchmark harness."""
from __future__ import annotations

import importlib.util
import json

import pytest

import eval_ruspellgold_harness as ruspellgold_harness
from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE
from eval_ruspellgold_harness import evaluate_all_modes, evaluate_mode


RAPIDFUZZ_AVAILABLE = importlib.util.find_spec("rapidfuzz") is not None
SYMSPELL_AVAILABLE = importlib.util.find_spec("symspellpy") is not None
ALL_BACKENDS_AVAILABLE = RAPIDFUZZ_AVAILABLE and SYMSPELL_AVAILABLE

EXPECTED_KEYS = {
    "total_cases",
    "exact_match_pass_count",
    "exact_match_pass_rate",
    "candidate_generated_total",
    "candidate_applied_total",
    "candidate_rejected_total",
    "candidate_rejected_no_result_total",
    "candidate_rejected_unsafe_candidate_total",
    "candidate_rejected_morph_blocked_total",
    "candidate_rejected_morph_unknown_total",
    "candidate_ambiguous_total",
    "candidate_ambiguous_tie_total",
    "candidate_shadow_skipped_total",
    "rollback_total",
}


def test_ruspellgold_harness_repeated_run_is_stable() -> None:
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


def test_ruspellgold_harness_aggregates_have_expected_shape() -> None:
    if not ALL_BACKENDS_AVAILABLE:
        baseline = evaluate_mode("baseline")
        assert set(baseline.keys()) == EXPECTED_KEYS
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
        assert set(mode_stats.keys()) == EXPECTED_KEYS
        assert 0 <= float(mode_stats["exact_match_pass_rate"]) <= 1.0
        assert int(mode_stats["candidate_rejected_total"]) == (
            int(mode_stats["candidate_rejected_no_result_total"])
            + int(mode_stats["candidate_rejected_unsafe_candidate_total"])
            + int(mode_stats["candidate_rejected_morph_blocked_total"])
            + int(mode_stats["candidate_rejected_morph_unknown_total"])
        )
        assert int(mode_stats["candidate_ambiguous_total"]) == int(mode_stats["candidate_ambiguous_tie_total"])


def test_ruspellgold_shadow_matches_baseline_and_apply_is_safe() -> None:
    baseline = evaluate_mode("baseline")

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

    assert rapidfuzz_shadow["total_cases"] == baseline["total_cases"]
    assert symspell_shadow["total_cases"] == baseline["total_cases"]
    assert rapidfuzz_apply["total_cases"] == baseline["total_cases"]
    assert symspell_apply["total_cases"] == baseline["total_cases"]

    assert rapidfuzz_shadow["candidate_applied_total"] == 0
    assert symspell_shadow["candidate_applied_total"] == 0
    assert rapidfuzz_shadow["exact_match_pass_count"] == baseline["exact_match_pass_count"]
    assert symspell_shadow["exact_match_pass_count"] == baseline["exact_match_pass_count"]

    assert rapidfuzz_apply["rollback_total"] == 0
    assert symspell_apply["rollback_total"] == 0
    assert rapidfuzz_apply["candidate_rejected_unsafe_candidate_total"] == 0
    assert symspell_apply["candidate_rejected_unsafe_candidate_total"] == 0


def test_ruspellgold_no_placeholder_leakage_in_serialized_output() -> None:
    if not ALL_BACKENDS_AVAILABLE:
        serialized = json.dumps(evaluate_mode("baseline"), ensure_ascii=False, sort_keys=True)
    else:
        serialized = json.dumps(evaluate_all_modes(), ensure_ascii=False, sort_keys=True)
    assert PLACEHOLDER_TEMPLATE.split("{index}")[0] not in serialized


def test_ruspellgold_fail_closed_on_broken_dataset_path(monkeypatch) -> None:
    monkeypatch.setenv("GRAMLYNX_RUSPELLGOLD_PATH", "/tmp/gramlynx_missing_ruspellgold.jsonl")
    with pytest.raises(FileNotFoundError):
        evaluate_all_modes()


def test_ruspellgold_fail_closed_on_broken_dataset_rows(monkeypatch, tmp_path) -> None:
    broken = tmp_path / "broken.jsonl"
    broken.write_text(
        "\n".join(
            [
                '{"input_text":"севодня","expected_clean_text":"сегодня"}',
                '{"input_text":123,"expected_clean_text":"сегодня"}',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_RUSPELLGOLD_PATH", str(broken))
    with pytest.raises(ValueError):
        evaluate_all_modes()


def test_ruspellgold_fail_closed_when_rapidfuzz_missing(monkeypatch) -> None:
    monkeypatch.setattr(ruspellgold_harness.importlib.util, "find_spec", lambda name: None if name == "rapidfuzz" else object())
    with pytest.raises(RuntimeError, match="rapidfuzz"):
        evaluate_mode("rapidfuzz_apply")


def test_ruspellgold_fail_closed_when_symspell_missing(monkeypatch) -> None:
    monkeypatch.setattr(ruspellgold_harness.importlib.util, "find_spec", lambda name: None if name == "symspellpy" else object())
    with pytest.raises(RuntimeError, match="symspellpy"):
        evaluate_mode("symspell_apply")


def test_ruspellgold_baseline_still_works_without_backend_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(ruspellgold_harness.importlib.util, "find_spec", lambda name: None)
    stats = evaluate_mode("baseline")
    assert int(stats["total_cases"]) > 0


def test_ruspellgold_symspell_v3_improves_over_v2_dictionary(monkeypatch) -> None:
    if not SYMSPELL_AVAILABLE:
        pytest.skip("symspellpy is not available")

    monkeypatch.setenv("GRAMLYNX_EVAL_DICTIONARY_SOURCE_RU", "app/resources/ru_dictionary_v2.txt")
    v2 = evaluate_mode("symspell_apply")

    monkeypatch.setenv("GRAMLYNX_EVAL_DICTIONARY_SOURCE_RU", "app/resources/ru_dictionary_v3.txt")
    v3 = evaluate_mode("symspell_apply")

    assert int(v3["candidate_rejected_no_result_total"]) < int(v2["candidate_rejected_no_result_total"])
    assert float(v3["exact_match_pass_rate"]) >= float(v2["exact_match_pass_rate"])
    assert int(v3["rollback_total"]) == 0
    assert int(v3["candidate_rejected_unsafe_candidate_total"]) == 0


def test_ruspellgold_backend_comparison_signal_is_informative() -> None:
    if not ALL_BACKENDS_AVAILABLE:
        with pytest.raises(RuntimeError):
            evaluate_mode("rapidfuzz_apply")
        with pytest.raises(RuntimeError):
            evaluate_mode("symspell_apply")
        return

    rapidfuzz_apply = evaluate_mode("rapidfuzz_apply")
    symspell_apply = evaluate_mode("symspell_apply")

    # Expanded benchmark should produce non-trivial candidate activity in both backends.
    assert int(rapidfuzz_apply["candidate_generated_total"]) > 0
    assert int(symspell_apply["candidate_generated_total"]) > 0

    # Backend profiles should differ on at least one diagnostic bucket.
    assert (
        int(rapidfuzz_apply["candidate_ambiguous_total"]) != int(symspell_apply["candidate_ambiguous_total"])
        or int(rapidfuzz_apply["candidate_generated_total"]) != int(symspell_apply["candidate_generated_total"])
        or int(rapidfuzz_apply["candidate_applied_total"]) != int(symspell_apply["candidate_applied_total"])
        or int(rapidfuzz_apply["exact_match_pass_count"]) != int(symspell_apply["exact_match_pass_count"])
    )
