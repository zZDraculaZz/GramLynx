from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CandidateOption:
    token: str
    rank: int = 0


@dataclass(frozen=True)
class SelectorContext:
    left_context: tuple[str, ...]
    original_token: str
    right_context: tuple[str, ...]


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: CandidateOption
    score: float


class CandidateScorer(Protocol):
    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float: ...
