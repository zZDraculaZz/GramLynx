from __future__ import annotations

from dataclasses import dataclass

from .interfaces import CandidateOption, CandidateScorer, ScoredCandidate, SelectorContext


@dataclass(frozen=True)
class SelectorOutcome:
    best_token: str | None
    best_score: float
    second_score: float
    scored: tuple[ScoredCandidate, ...]


class ContextAwareSelector:
    """V2 scaffold: context-aware selector interface, model-agnostic."""

    def choose(
        self,
        *,
        context: SelectorContext,
        candidates: tuple[CandidateOption, ...],
        scorer: CandidateScorer,
    ) -> SelectorOutcome:
        if not candidates:
            return SelectorOutcome(best_token=None, best_score=0.0, second_score=float("-inf"), scored=tuple())

        scored = tuple(
            ScoredCandidate(candidate=c, score=float(scorer.score_candidate(context, c)))
            for c in candidates
        )
        ordered = tuple(sorted(scored, key=lambda row: row.score, reverse=True))
        best = ordered[0]
        second = ordered[1].score if len(ordered) > 1 else float("-inf")
        return SelectorOutcome(
            best_token=best.candidate.token,
            best_score=best.score,
            second_score=second,
            scored=ordered,
        )
