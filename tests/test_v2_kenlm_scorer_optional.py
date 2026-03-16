from __future__ import annotations

import importlib.util

import pytest

from app.core.v2 import CandidateOption, KenLMScorer, SelectorContext
from research.context_rerank_v1.scorers.kenlm import KenLMScorer as ResearchKenLMScorer


def _kenlm_backend_available() -> bool:
    return importlib.util.find_spec("kenlm") is not None


KENLM_REQUIRED = pytest.mark.skipif(
    not _kenlm_backend_available(),
    reason="kenlm backend is not available in this environment",
)


@KENLM_REQUIRED
def test_kenlm_scorer_prefers_contextually_correct_candidate(tmp_path) -> None:
    kenlm = pytest.importorskip("kenlm")
    assert kenlm is not None

    arpa = tmp_path / "tiny.arpa"
    ResearchKenLMScorer.train_bigram_arpa(("я дома", "я дома", "я дом"), arpa)

    scorer = KenLMScorer(arpa)
    context = SelectorContext(left_context=("я",), original_token="дома", right_context=tuple())

    good = scorer.score_candidate(context, CandidateOption(token="дома", rank=0))
    bad = scorer.score_candidate(context, CandidateOption(token="дом", rank=0))

    assert good > bad
