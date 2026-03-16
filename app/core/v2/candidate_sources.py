from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from symspellpy import SymSpell, Verbosity

from .interfaces import CandidateOption


@dataclass
class SymSpellCandidateSource:
    dictionary_path: Path
    max_candidates: int = 5
    max_edit_distance: int = 2
    include_original: bool = True

    def __post_init__(self) -> None:
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")
        if self.max_edit_distance < 0:
            raise ValueError("max_edit_distance must be >= 0")

        symspell = SymSpell(max_dictionary_edit_distance=self.max_edit_distance, prefix_length=7)
        loaded = symspell.load_dictionary(str(self.dictionary_path), term_index=0, count_index=1)
        if not loaded:
            raise ValueError(f"failed to load dictionary: {self.dictionary_path}")
        self._symspell = symspell

    def candidates_for_token(self, token: str) -> tuple[CandidateOption, ...]:
        suggestions = self._symspell.lookup(
            token,
            Verbosity.CLOSEST,
            max_edit_distance=self.max_edit_distance,
            include_unknown=False,
            transfer_casing=False,
        )

        rows: dict[str, CandidateOption] = {}
        for suggestion in suggestions:
            if not suggestion.term:
                continue
            rank = int(suggestion.count) if int(suggestion.count) > 0 else -int(suggestion.distance)
            rows[suggestion.term] = CandidateOption(token=suggestion.term, rank=rank)

        if self.include_original and token not in rows:
            rows[token] = CandidateOption(token=token, rank=0)

        ordered = sorted(rows.values(), key=lambda row: (row.rank, row.token), reverse=True)
        return tuple(ordered[: self.max_candidates])
