from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any



@dataclass(frozen=True)
class Candidate:
    term: str
    distance: int


class LargeLexiconCandidateSource:
    """Top-k candidate extraction from lexicon sources for offline experiments."""

    def __init__(
        self,
        dictionary_path: str | Path,
        top_k: int = 5,
        max_edit_distance: int = 2,
        extra_dictionary_paths: tuple[str | Path, ...] = tuple(),
    ) -> None:
        self._dictionary_path = Path(dictionary_path)
        self._extra_dictionary_paths = tuple(Path(p) for p in extra_dictionary_paths)
        self._top_k = top_k
        self._max_edit_distance = max_edit_distance
        self._terms = self._load_terms_from_paths((self._dictionary_path, *self._extra_dictionary_paths))
        self._symspell = self._build_symspell(self._terms)

    @staticmethod
    def _normalize_token(token: str) -> str:
        return token.strip().lower().replace("ё", "е")

    @staticmethod
    def _build_symspell(terms: tuple[str, ...]) -> Any | None:
        try:
            from symspellpy import SymSpell
        except Exception:
            return None

        if not terms:
            return None

        symspell = SymSpell(max_dictionary_edit_distance=3, prefix_length=7)

        for rank, term in enumerate(terms):
            # deterministic pseudo-frequency for stable ordering
            symspell.create_dictionary_entry(term, max(1, len(terms) - rank))
        return symspell

    @staticmethod
    def _load_terms(path: Path) -> tuple[str, ...]:
        if not path.exists():
            return tuple()
        terms: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            token = line.split("\t", maxsplit=1)[0].strip()
            if token.startswith("#"):
                continue
            token = LargeLexiconCandidateSource._normalize_token(token)
            if token:
                terms.append(token)
        return tuple(dict.fromkeys(terms))

    @staticmethod
    def _load_terms_from_paths(paths: tuple[Path, ...]) -> tuple[str, ...]:
        merged: list[str] = []
        for path in paths:
            merged.extend(LargeLexiconCandidateSource._load_terms(path))
        return tuple(dict.fromkeys(merged))

    def _effective_max_edit_distance(self, token_norm: str) -> int:
        if self._max_edit_distance >= 3 and len(token_norm) >= 9:
            return 3
        return self._max_edit_distance

    def top_k(self, token: str) -> tuple[Candidate, ...]:
        token_norm = self._normalize_token(token)
        if not token_norm:
            return tuple()
        if not re.fullmatch(r"[а-яе-]+", token_norm):
            return tuple()

        if self._symspell is not None:
            return self._top_k_symspell(token_norm)

        return self._top_k_fallback(token_norm)

    def _top_k_symspell(self, token_norm: str) -> tuple[Candidate, ...]:
        from symspellpy import Verbosity

        max_dist = self._effective_max_edit_distance(token_norm)
        suggestions = self._symspell.lookup(  # type: ignore[union-attr]
            token_norm,
            Verbosity.ALL,
            max_edit_distance=max_dist,
            include_unknown=False,
            transfer_casing=False,
        )
        out = [Candidate(term=s.term, distance=int(s.distance)) for s in suggestions if s.term != token_norm and int(s.distance) <= max_dist]
        out.sort(key=lambda c: (c.distance, c.term))
        return tuple(out[: self._top_k])

    def _top_k_fallback(self, token_norm: str) -> tuple[Candidate, ...]:
        if token_norm in self._terms:
            return tuple()

        scored: list[Candidate] = []
        max_dist = self._effective_max_edit_distance(token_norm)
        for term in self._terms:
            dist = _levenshtein_distance(token_norm, term)
            if dist <= max_dist:
                scored.append(Candidate(term=term, distance=dist))

        scored.sort(key=lambda item: (item.distance, abs(len(item.term) - len(token_norm)), item.term))
        return tuple(scored[: self._top_k])


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    prev_row = list(range(len(right) + 1))
    for i, c_left in enumerate(left, start=1):
        curr_row = [i]
        for j, c_right in enumerate(right, start=1):
            cost = 0 if c_left == c_right else 1
            curr_row.append(
                min(
                    prev_row[j] + 1,
                    curr_row[j - 1] + 1,
                    prev_row[j - 1] + cost,
                )
            )
        prev_row = curr_row
    return prev_row[-1]
