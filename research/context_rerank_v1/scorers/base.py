from __future__ import annotations

from abc import ABC, abstractmethod


class SentenceCandidateScorer(ABC):
    """Sentence-level scorer abstraction for candidate reranking."""

    @abstractmethod
    def score(self, tokens: tuple[str, ...], position: int, candidate: str) -> float:
        """Return candidate score for token replacement at position in a sentence."""
