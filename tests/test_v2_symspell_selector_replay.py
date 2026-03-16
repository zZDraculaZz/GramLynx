from __future__ import annotations

from pathlib import Path

from app.core.v2 import SymSpellCandidateSource
from app.core.v2.interfaces import CandidateOption, SelectorContext
from app.core.v2.offline_eval import load_text_clean_cases, run_symspell_selector_replay


class _HeuristicTokenScorer:
    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        if context.original_token == "атк":
            if candidate.token == "акт":
                return 0.51
            if candidate.token == "атк":
                return 0.50
        return float(candidate.rank)


def _write_dictionary(path: Path) -> None:
    path.write_text("дилемму 100\nпривет 120\nакт 40\n", encoding="utf-8")


def test_run_symspell_selector_replay_micro_fixture(tmp_path: Path) -> None:
    dictionary = tmp_path / "tiny_dict.txt"
    _write_dictionary(dictionary)

    cases = load_text_clean_cases(Path("tests/cases/v2_symspell_selector_micro.jsonl"))
    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)

    summary = run_symspell_selector_replay(
        cases,
        symspell_source=source,
        scorer=_HeuristicTokenScorer(),
        max_candidates=5,
        min_margin=0.05,
    )

    assert summary["total_cases"] == 4
    assert summary["changed_count"] == 2
    assert summary["kept_original_count"] == 2
    assert summary["expected_match_when_changed_rate"] == 1.0

    reasons = summary["decision_reason_counts"]
    assert isinstance(reasons, dict)
    assert reasons.get("apply_candidate", 0) == 2
    assert reasons.get("low_margin", 0) == 1
