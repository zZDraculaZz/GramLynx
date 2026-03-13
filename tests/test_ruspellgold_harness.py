"""Tests for offline RuSpellGold-style benchmark harness."""
from __future__ import annotations

import json

import pytest

from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE
from eval_ruspellgold_harness import evaluate_all_modes, evaluate_mode


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
    first = evaluate_all_modes()
    second = evaluate_all_modes()
    assert first == second


def test_ruspellgold_harness_aggregates_have_expected_shape() -> None:
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
