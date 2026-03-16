from __future__ import annotations

from pathlib import Path

from app.core.v2.offline_eval import (
    compare_replay_summaries,
    load_replay_cases,
    load_text_clean_cases,
    load_text_clean_yaml_smart,
    replay_cases,
    summarize_replay,
)


def test_load_replay_cases_and_replay_results() -> None:
    cases = load_replay_cases(Path("tests/cases/v2_selector_replay_micro.jsonl"))
    assert len(cases) == 2

    results = replay_cases(cases, min_confidence=0.1, min_margin=0.05)
    by_id = {row.case_id: row for row in results}

    assert by_id["apply_candidate_when_confident"].selected_token == "сегодня"
    assert by_id["apply_candidate_when_confident"].reason == "apply_candidate"

    assert by_id["fail_closed_low_margin"].selected_token == "превет"
    assert by_id["fail_closed_low_margin"].reason == "low_margin"


def test_summarize_replay_counts_expected_matches() -> None:
    cases = load_replay_cases(Path("tests/cases/v2_selector_replay_micro.jsonl"))
    results = replay_cases(cases, min_confidence=0.1, min_margin=0.05)
    summary = summarize_replay(results)

    assert summary["total_cases"] == 2
    assert summary["expected_match_count"] == 2
    assert summary["expected_match_rate"] == 1.0
    assert summary["changed_count"] == 1
    assert summary["kept_original_count"] == 1
    assert summary["expected_match_when_changed_count"] == 1
    assert summary["expected_match_when_changed_rate"] == 1.0
    assert summary["decision_reason_counts"] == {"apply_candidate": 1, "low_margin": 1}


def test_load_text_clean_yaml_smart_reads_cases(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.yml"
    dataset.write_text(
        "smart:\n"
        "  - input: севодня будет встреча\n"
        "    expected_clean_text: сегодня будет встреча\n",
        encoding="utf-8",
    )

    rows = load_text_clean_yaml_smart(dataset)
    assert len(rows) == 1
    assert rows[0].input_text == "севодня будет встреча"
    assert rows[0].expected_clean_text == "сегодня будет встреча"


def test_load_text_clean_cases_dispatches_jsonl_with_input_alias(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text('{"input":"тест","expected_clean_text":"тест"}\n', encoding="utf-8")

    rows = load_text_clean_cases(dataset)
    assert len(rows) == 1
    assert rows[0].input_text == "тест"
    assert rows[0].expected_clean_text == "тест"


def test_compare_replay_summaries_returns_compact_deltas() -> None:
    baseline = {
        "expected_match_count": 1,
        "expected_match_rate": 0.5,
        "expected_match_when_changed_count": 0,
        "expected_match_when_changed_rate": 0.0,
        "changed_count": 1,
        "kept_original_count": 1,
        "decision_reason_counts": {"low_margin": 1, "apply_candidate": 0},
    }
    challenger = {
        "expected_match_count": 2,
        "expected_match_rate": 1.0,
        "expected_match_when_changed_count": 1,
        "expected_match_when_changed_rate": 1.0,
        "changed_count": 1,
        "kept_original_count": 1,
        "decision_reason_counts": {"low_margin": 0, "apply_candidate": 1},
    }

    delta = compare_replay_summaries(baseline, challenger)

    assert delta["expected_match_count_delta"] == 1
    assert delta["expected_match_rate_delta"] == 0.5
    assert delta["expected_match_when_changed_count_delta"] == 1
    assert delta["expected_match_when_changed_rate_delta"] == 1.0
    assert delta["changed_count_delta"] == 0
    assert delta["kept_original_count_delta"] == 0
    assert delta["decision_reason_counts_delta"] == {"apply_candidate": 1, "low_margin": -1}
