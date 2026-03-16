from __future__ import annotations

from dataclasses import dataclass

from .decision import FailClosedDecisionLayer, SelectionDecision
from .interfaces import CandidateOption, CandidateScorer, SelectorContext
from .selector import ContextAwareSelector


@dataclass(frozen=True)
class V2SelectorScaffold:
    """GramLynx v2 scaffold.

    Non-default architectural path for context-aware candidate selection.
    Must coexist with baseline and stay opt-in until explicit enablement.
    """

    selector: ContextAwareSelector
    decision: FailClosedDecisionLayer

    def evaluate_token(
        self,
        *,
        context: SelectorContext,
        candidates: tuple[CandidateOption, ...],
        scorer: CandidateScorer,
    ) -> SelectionDecision:
        outcome = self.selector.choose(context=context, candidates=candidates, scorer=scorer)
        return self.decision.decide(
            original_token=context.original_token,
            best_token=outcome.best_token,
            best_score=outcome.best_score,
            second_score=outcome.second_score,
        )


def make_v2_selector_scaffold(*, min_confidence: float = 0.0, min_margin: float = 0.0) -> V2SelectorScaffold:
    return V2SelectorScaffold(
        selector=ContextAwareSelector(),
        decision=FailClosedDecisionLayer(min_confidence=min_confidence, min_margin=min_margin),
    )
