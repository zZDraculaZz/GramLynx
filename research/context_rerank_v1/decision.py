from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionResult:
    output_token: str
    applied: bool
    reason: str


def fail_closed_pick(
    original_token: str,
    scored_candidates: tuple[tuple[str, float], ...],
    min_margin: float,
    min_abs_score: float,
) -> DecisionResult:
    if not scored_candidates:
        return DecisionResult(output_token=original_token, applied=False, reason="no_candidates")

    ranked = sorted(scored_candidates, key=lambda item: (-item[1], item[0]))
    best_token, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else float("-inf")

    if best_score < min_abs_score:
        return DecisionResult(output_token=original_token, applied=False, reason="low_abs_score")

    if second_score != float("-inf") and (best_score - second_score) < min_margin:
        return DecisionResult(output_token=original_token, applied=False, reason="low_margin")

    if best_token == original_token:
        return DecisionResult(output_token=original_token, applied=False, reason="same_as_original")

    return DecisionResult(output_token=best_token, applied=True, reason="applied")
