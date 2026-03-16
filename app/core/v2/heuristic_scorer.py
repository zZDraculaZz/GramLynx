from __future__ import annotations

from .interfaces import CandidateOption, SelectorContext


class ContextWindowHeuristicScorer:
    """Tiny deterministic context-window scorer for offline control comparisons.

    Offline/dev control line only; not a runtime /clean scorer.
    """

    _LEFT_HINTS: dict[str, tuple[str, float]] = {
        "до": ("а", 0.7),
        "эту": ("у", 0.7),
        "иду": ("й", 0.6),
        "наша": ("а", 0.6),
        "мой": ("к", 0.4),
    }
    _RIGHT_HINTS: dict[str, tuple[str, float]] = {
        "встречи": ("а", 0.4),
        "решили": ("у", 0.4),
        "дождь": ("я", 0.3),
        "план": ("к", 0.3),
    }

    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        token = candidate.token.lower()
        score = -0.01 * float(candidate.rank)

        if context.left_context:
            left = context.left_context[-1].lower()
            if left in self._LEFT_HINTS:
                ending, bonus = self._LEFT_HINTS[left]
                if token.endswith(ending):
                    score += bonus
            if token == left:
                score -= 0.25

        if context.right_context:
            right = context.right_context[0].lower()
            if right in self._RIGHT_HINTS:
                ending, bonus = self._RIGHT_HINTS[right]
                if token.endswith(ending):
                    score += bonus
            if token == right:
                score -= 0.25

        return score
