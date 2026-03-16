from __future__ import annotations

import importlib.util
from pathlib import Path

from .interfaces import CandidateOption, SelectorContext


def is_kenlm_available() -> bool:
    return importlib.util.find_spec("kenlm") is not None


class KenLMScorer:
    """Optional offline KenLM scorer for token-candidate ranking in context."""

    def __init__(self, model_path: str | Path) -> None:
        if not is_kenlm_available():
            raise RuntimeError("kenlm backend is not available")
        import kenlm  # type: ignore

        self._model = kenlm.Model(str(model_path))

    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        tokens = [*context.left_context, candidate.token, *context.right_context]
        if not tokens:
            return 0.0
        return float(self._model.score(" ".join(tokens), bos=True, eos=True))
