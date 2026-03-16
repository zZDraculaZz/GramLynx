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
        enable_retrieval_normalization: bool = True,
    ) -> None:
        self._dictionary_path = Path(dictionary_path)
        self._extra_dictionary_paths = tuple(Path(p) for p in extra_dictionary_paths)
        self._top_k = top_k
        self._max_edit_distance = max_edit_distance
        self._enable_retrieval_normalization = bool(enable_retrieval_normalization)
        self._raw_terms = self._load_raw_terms_from_paths((self._dictionary_path, *self._extra_dictionary_paths))
        self._terms = tuple(dict.fromkeys(self._normalize_token(t) for t in self._raw_terms if self._normalize_token(t)))
        self._yo_variants_by_norm = self._build_yo_variants(self._raw_terms)
        self._symspell = self._build_symspell(self._terms)

    @staticmethod
    def _normalize_token(token: str) -> str:
        return token.strip().lower().replace("ё", "е")

    @staticmethod
    def _surface_token(token: str) -> str:
        return token.strip().lower()

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
            symspell.create_dictionary_entry(term, max(1, len(terms) - rank))
        return symspell

    @staticmethod
    def _load_raw_terms(path: Path) -> tuple[str, ...]:
        if not path.exists():
            return tuple()
        terms: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            token = line.split("\t", maxsplit=1)[0].strip()
            if token.startswith("#"):
                continue
            token = LargeLexiconCandidateSource._surface_token(token)
            if token:
                terms.append(token)
        return tuple(dict.fromkeys(terms))

    @staticmethod
    def _load_raw_terms_from_paths(paths: tuple[Path, ...]) -> tuple[str, ...]:
        merged: list[str] = []
        for path in paths:
            merged.extend(LargeLexiconCandidateSource._load_raw_terms(path))
        return tuple(dict.fromkeys(merged))

    @staticmethod
    def _build_yo_variants(raw_terms: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
        mapping: dict[str, list[str]] = {}
        for term in raw_terms:
            if "ё" not in term:
                continue
            key = LargeLexiconCandidateSource._normalize_token(term)
            mapping.setdefault(key, []).append(term)
        return {k: tuple(dict.fromkeys(v)) for k, v in mapping.items()}

    @staticmethod
    def _lookup_variants(token: str) -> tuple[str, ...]:
        token = token.strip()
        variants = [token]
        stripped = token.strip("`*_~|<>{}[]()\"'")
        if stripped and stripped not in variants:
            variants.append(stripped)
        if token.startswith("#") or token.startswith("@"):
            bare = token[1:]
            if bare and bare not in variants:
                variants.append(bare)

        base = stripped or token
        compact = base.replace("-", "")
        if compact and compact not in variants:
            variants.append(compact)

        # Narrow hyphen restoration for frequent noisy user-text compounds.
        if "-" not in compact:
            for prefix in ("по", "из"):
                if compact.startswith(prefix) and len(compact) >= len(prefix) + 3:
                    hyphenated = f"{prefix}-{compact[len(prefix):]}"
                    if hyphenated not in variants:
                        variants.append(hyphenated)

        return tuple(variants)

    def _effective_max_edit_distance(self, token_norm: str) -> int:
        if self._max_edit_distance >= 3 and len(token_norm) >= 9:
            return 3
        return self._max_edit_distance

    def top_k(self, token: str) -> tuple[Candidate, ...]:
        merged: dict[str, Candidate] = {}
        lookup_variants = self._lookup_variants(token) if self._enable_retrieval_normalization else (token,)
        for variant in lookup_variants:
            token_norm = self._normalize_token(variant)
            if not token_norm:
                continue
            if not re.fullmatch(r"[а-яёе-]+", token_norm):
                continue
            rows = self._top_k_symspell(token_norm) if self._symspell is not None else self._top_k_fallback(token_norm)
            for row in rows:
                prev = merged.get(row.term)
                if prev is None or row.distance < prev.distance:
                    merged[row.term] = row
            if self._enable_retrieval_normalization:
                for yo in self._yo_variants_by_norm.get(token_norm, tuple()):
                    prev = merged.get(yo)
                    cand = Candidate(term=yo, distance=0)
                    if prev is None or cand.distance < prev.distance:
                        merged[yo] = cand
        ordered = sorted(merged.values(), key=lambda c: (c.distance, abs(len(c.term) - len(self._normalize_token(token))), c.term))
        return tuple(ordered[: self._top_k])

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
        if self._enable_retrieval_normalization:
            out.extend(Candidate(term=yo, distance=0) for yo in self._yo_variants_by_norm.get(token_norm, tuple()))
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
