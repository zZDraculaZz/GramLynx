from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectionDecision:
    selected_token: str
    changed: bool
    reason: str
    confidence: float
    margin: float


@dataclass(frozen=True)
class FailClosedDecisionLayer:
    min_confidence: float = 0.0
    min_margin: float = 0.0

    def decide(
        self,
        *,
        original_token: str,
        best_token: str | None,
        best_score: float,
        second_score: float,
    ) -> SelectionDecision:
        if not best_token:
            return SelectionDecision(
                selected_token=original_token,
                changed=False,
                reason="no_candidate",
                confidence=best_score,
                margin=0.0,
            )

        margin = best_score - second_score
        if best_score < self.min_confidence:
            return SelectionDecision(
                selected_token=original_token,
                changed=False,
                reason="low_confidence",
                confidence=best_score,
                margin=margin,
            )

        if margin < self.min_margin:
            return SelectionDecision(
                selected_token=original_token,
                changed=False,
                reason="low_margin",
                confidence=best_score,
                margin=margin,
            )

        if best_token == original_token:
            return SelectionDecision(
                selected_token=original_token,
                changed=False,
                reason="original_wins",
                confidence=best_score,
                margin=margin,
            )

        return SelectionDecision(
            selected_token=best_token,
            changed=True,
            reason="apply_candidate",
            confidence=best_score,
            margin=margin,
        )
