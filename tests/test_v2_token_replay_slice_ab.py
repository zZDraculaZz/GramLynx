from __future__ import annotations

from pathlib import Path

from app.core.v2 import SymSpellCandidateSource
from app.core.v2.interfaces import CandidateOption, SelectorContext
from app.core.v2.offline_eval import RankBasedScorer, load_text_clean_cases, run_ab_replay_and_compare, run_symspell_selector_replay


class _ReverseRankScorer:
    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return -float(candidate.rank)


def _write_dictionary(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "привет 200",
                "дилемму 140",
                "сегодня 220",
                "завтра 210",
                "пожалуйста 250",
                "домой 180",
                "встреча 170",
                "тест 160",
                "акт 90",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_token_replay_slice_runs_and_ab_compare_is_deterministic(tmp_path: Path) -> None:
    # Curated token-level replay slice: offline-only, not a replacement for full RuSpellGold.
    cases = load_text_clean_cases(Path("tests/cases/v2_token_replay_slice_a.jsonl"))
    assert len(cases) == 10

    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)
    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)

    summary = run_symspell_selector_replay(cases, symspell_source=source, scorer=RankBasedScorer(), max_candidates=5)
    required = {
        "total_cases",
        "expected_match_count",
        "expected_match_rate",
        "changed_count",
        "kept_original_count",
        "expected_match_when_changed_count",
        "expected_match_when_changed_rate",
        "decision_reason_counts",
    }
    assert required.issubset(summary.keys())
    assert summary["total_cases"] == len(cases)

    delta1 = run_ab_replay_and_compare(
        cases,
        symspell_source=source,
        scorer_a=RankBasedScorer(),
        scorer_b=_ReverseRankScorer(),
        max_candidates=5,
    )
    delta2 = run_ab_replay_and_compare(
        cases,
        symspell_source=source,
        scorer_a=RankBasedScorer(),
        scorer_b=_ReverseRankScorer(),
        max_candidates=5,
    )

    assert delta1 == delta2
    assert "decision_reason_counts_delta" in delta1
    assert isinstance(delta1["decision_reason_counts_delta"], dict)
