from __future__ import annotations

from pathlib import Path

import pytest

from app.core.v2 import SymSpellCandidateSource
from app.core.v2.interfaces import CandidateOption, SelectorContext
from app.core.v2.offline_eval import compare_replay_summaries, load_text_clean_cases, run_symspell_selector_replay


class _RankScorer:
    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return float(candidate.rank)


class _ReverseRankScorer:
    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return -float(candidate.rank)


def _write_dictionary(path: Path) -> None:
    path.write_text("дилемму 100\nпривет 120\nакт 40\n", encoding="utf-8")


def test_compare_replay_summaries_rejects_total_cases_mismatch() -> None:
    with pytest.raises(ValueError, match="total_cases mismatch"):
        compare_replay_summaries(
            {"total_cases": 1, "decision_reason_counts": {}},
            {"total_cases": 2, "decision_reason_counts": {}},
        )


def test_compare_replay_summaries_with_two_scorers_detects_deltas(tmp_path: Path) -> None:
    dictionary = tmp_path / "tiny_dict.txt"
    _write_dictionary(dictionary)

    cases = load_text_clean_cases(Path("tests/cases/v2_symspell_selector_micro.jsonl"))
    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)

    summary_a = run_symspell_selector_replay(
        cases,
        symspell_source=source,
        scorer=_RankScorer(),
        max_candidates=5,
        min_margin=0.0,
    )
    summary_b = run_symspell_selector_replay(
        cases,
        symspell_source=source,
        scorer=_ReverseRankScorer(),
        max_candidates=5,
        min_margin=0.0,
    )

    delta = compare_replay_summaries(summary_a, summary_b)

    assert "expected_match_rate_delta" in delta
    assert "expected_match_when_changed_rate_delta" in delta
    assert "changed_count_delta" in delta
    assert "kept_original_count_delta" in delta
    assert "decision_reason_counts_delta" in delta
    assert isinstance(delta["decision_reason_counts_delta"], dict)
    assert any(
        delta[key] != 0
        for key in (
            "expected_match_count_delta",
            "expected_match_rate_delta",
            "changed_count_delta",
            "kept_original_count_delta",
            "expected_match_when_changed_count_delta",
            "expected_match_when_changed_rate_delta",
        )
    )
