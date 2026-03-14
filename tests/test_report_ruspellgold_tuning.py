from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import report_ruspellgold_tuning as tuning_report


def test_generate_tuning_report_has_required_sections(monkeypatch, tmp_path: Path) -> None:
    safe_summary = {
        "total_cases": 3,
        "exact_match_pass_count": 1,
        "exact_match_pass_rate": 0.333333,
        "candidate_generated_total": 0,
        "candidate_applied_total": 0,
    }
    smart_summary = {
        "total_cases": 3,
        "exact_match_pass_count": 2,
        "exact_match_pass_rate": 0.666667,
        "candidate_generated_total": 3,
        "candidate_applied_total": 1,
    }
    for key in (
        "candidate_rejected_total",
        "candidate_rejected_no_result_total",
        "candidate_rejected_unsafe_candidate_total",
        "candidate_rejected_morph_blocked_total",
        "candidate_rejected_morph_unknown_total",
        "candidate_ambiguous_total",
        "candidate_ambiguous_tie_total",
        "candidate_shadow_skipped_total",
        "rollback_total",
    ):
        safe_summary[key] = 0
        smart_summary[key] = 0

    safe_rows = [
        {
            "exact_match": True,
            "expected_change": False,
            "unchanged_when_expected_change": False,
            "wrong_change": False,
            "no_change_as_expected": True,
            "candidate_generated_count": 0,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 0,
            "candidate_rejected_unsafe_candidate_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_ambiguous_count": 0,
            "candidate_ambiguous_tie_count": 0,
            "rollback_applied": False,
        },
        {
            "exact_match": False,
            "expected_change": True,
            "unchanged_when_expected_change": True,
            "wrong_change": False,
            "no_change_as_expected": False,
            "candidate_generated_count": 0,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 0,
            "candidate_rejected_unsafe_candidate_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_ambiguous_count": 0,
            "candidate_ambiguous_tie_count": 0,
            "rollback_applied": False,
        },
        {
            "exact_match": False,
            "expected_change": True,
            "unchanged_when_expected_change": False,
            "wrong_change": True,
            "no_change_as_expected": False,
            "candidate_generated_count": 0,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 0,
            "candidate_rejected_unsafe_candidate_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_ambiguous_count": 0,
            "candidate_ambiguous_tie_count": 0,
            "rollback_applied": False,
        },
    ]

    smart_rows = [
        {
            "exact_match": True,
            "expected_change": False,
            "unchanged_when_expected_change": False,
            "wrong_change": False,
            "no_change_as_expected": True,
            "candidate_generated_count": 1,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 1,
            "candidate_rejected_unsafe_candidate_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_ambiguous_count": 0,
            "candidate_ambiguous_tie_count": 0,
            "rollback_applied": False,
        },
        {
            "exact_match": True,
            "expected_change": True,
            "unchanged_when_expected_change": False,
            "wrong_change": False,
            "no_change_as_expected": False,
            "candidate_generated_count": 1,
            "candidate_applied_count": 1,
            "candidate_rejected_no_result_count": 0,
            "candidate_rejected_unsafe_candidate_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_ambiguous_count": 0,
            "candidate_ambiguous_tie_count": 0,
            "rollback_applied": False,
        },
        {
            "exact_match": False,
            "expected_change": True,
            "unchanged_when_expected_change": False,
            "wrong_change": True,
            "no_change_as_expected": False,
            "candidate_generated_count": 1,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 0,
            "candidate_rejected_unsafe_candidate_count": 1,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_ambiguous_count": 1,
            "candidate_ambiguous_tie_count": 0,
            "rollback_applied": True,
        },
    ]

    def fake_eval(mode_label: str):
        if mode_label == "baseline":
            return safe_summary, safe_rows
        if mode_label == "symspell_apply":
            return smart_summary, smart_rows
        raise AssertionError(f"unexpected mode: {mode_label}")

    monkeypatch.setattr(tuning_report, "_evaluate_cases_for_mode", fake_eval)

    output_md = tmp_path / "report.md"
    output_json = tmp_path / "report.json"
    result = tuning_report.generate_tuning_report(output_md=output_md, output_json=output_json)

    assert result["safe_vs_smart_diff"]["exact_match_pass_count_delta"] == 1
    assert result["safe_counts"]["unchanged_when_expected_change"] == 1
    assert result["smart_counts"]["unsafe_rejected"] == 1
    assert result["top_mismatch_slices"]["smart_baseline"]

    md = output_md.read_text(encoding="utf-8")
    assert "# RuSpellGold Tuning Report (safe default vs smart baseline)" in md
    assert "## Baseline summary" in md
    assert "## Safe vs smart diff" in md
    assert "## Outcome buckets (counts and rates)" in md
    assert "## Top high-signal mismatch slices" in md
    assert "## recommended next minimal tuning directions" in md

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "safe_summary" in payload
    assert "smart_summary" in payload
    assert "safe_vs_smart_diff" in payload
    assert "recommended_next_minimal_tuning_directions" in payload


def test_top_mismatch_slices_non_degenerate() -> None:
    rows = [
        {
            "exact_match": False,
            "unchanged_when_expected_change": True,
            "wrong_change": False,
            "candidate_generated_count": 1,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 1,
            "candidate_ambiguous_count": 0,
            "candidate_ambiguous_tie_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_rejected_unsafe_candidate_count": 0,
            "rollback_applied": False,
        },
        {
            "exact_match": False,
            "unchanged_when_expected_change": False,
            "wrong_change": True,
            "candidate_generated_count": 1,
            "candidate_applied_count": 0,
            "candidate_rejected_no_result_count": 0,
            "candidate_ambiguous_count": 1,
            "candidate_ambiguous_tie_count": 0,
            "candidate_rejected_morph_blocked_count": 0,
            "candidate_rejected_morph_unknown_count": 0,
            "candidate_rejected_unsafe_candidate_count": 1,
            "rollback_applied": True,
        },
    ]

    slices = tuning_report._top_mismatch_slices(rows, top_n=3)

    assert len(slices) == 2
    assert slices[0]["count"] >= 1
    assert "slice" in slices[0]


def test_preflight_missing_backend_message_is_actionable() -> None:
    message = tuning_report._diagnose_runtime_error(
        RuntimeError("candidate backend unavailable: symspellpy is not installed")
    )

    assert "missing candidate backend dependency" in message
    assert "symspellpy and rapidfuzz" in message
    assert "python -m pip install symspellpy rapidfuzz" in message
    assert "without full safe-vs-smart run, tuning changes must not be made" in message


def test_wrong_invocation_hint_points_to_canonical_command(monkeypatch) -> None:
    monkeypatch.setattr(tuning_report, "__package__", "")

    hint = tuning_report._wrong_invocation_hint()

    assert hint is not None
    assert "recommended invocation" in hint
    assert "python -m tests.report_ruspellgold_tuning" in hint


def test_canonical_module_invocation_help_works() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tests.report_ruspellgold_tuning", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "command: python -m tests.report_ruspellgold_tuning" in proc.stdout
    assert "--output-md" in proc.stdout
    assert "--output-json" in proc.stdout
