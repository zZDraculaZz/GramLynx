from __future__ import annotations

from pathlib import Path

import pytest

from app.core.v2 import CandidateOption, KenLMScorer, SelectorContext, SymSpellCandidateSource, is_kenlm_available
from app.core.v2.offline_eval import RankBasedScorer, TextCleanCase, run_slice_scorer_comparison
from research.context_rerank_v1.scorers.kenlm import KenLMScorer as ResearchKenLMScorer


class _ReverseRankScorer:
    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return -float(candidate.rank)


def _write_slice_dictionary(path: Path) -> None:
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


def test_run_slice_scorer_comparison_is_deterministic_and_non_zero(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_slice_dictionary(dictionary)
    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)

    result = run_slice_scorer_comparison(
        Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        symspell_source=source,
        scorer_a=RankBasedScorer(),
        scorer_b=_ReverseRankScorer(),
        max_candidates=5,
    )

    summary_a = result["summary_a"]
    summary_b = result["summary_b"]
    delta = result["delta"]

    assert summary_a["total_cases"] == 10
    assert summary_b["total_cases"] == 10

    assert "decision_reason_counts_delta" in delta
    assert "expected_match_rate_delta" in delta
    assert isinstance(delta["decision_reason_counts_delta"], dict)
    assert delta["expected_match_count_delta"] != 0


KENLM_REQUIRED = pytest.mark.skipif(
    not is_kenlm_available(),
    reason="kenlm backend is not available in this environment",
)


@KENLM_REQUIRED
def test_run_slice_scorer_comparison_with_kenlm_optional_path(tmp_path: Path) -> None:
    arpa = tmp_path / "tiny.arpa"
    ResearchKenLMScorer.train_bigram_arpa(("я дома", "я дома", "сегодня тест"), arpa)

    dictionary = tmp_path / "kenlm_dict.txt"
    dictionary.write_text("дома 200\nдом 190\nсегодня 180\nтест 170\n", encoding="utf-8")
    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)

    cases = (
        TextCleanCase(input_text="дома", expected_clean_text="дома", left_context=("я",), right_context=tuple()),
        TextCleanCase(input_text="тест", expected_clean_text="тест", left_context=("сегодня",), right_context=tuple()),
    )

    result = run_slice_scorer_comparison(
        cases,
        symspell_source=source,
        scorer_a=RankBasedScorer(),
        scorer_b=KenLMScorer(arpa),
        max_candidates=5,
    )

    assert result["summary_a"]["total_cases"] == len(cases)
    assert result["summary_b"]["total_cases"] == len(cases)
    assert isinstance(result["delta"], dict)
    assert "decision_reason_counts_delta" in result["delta"]
