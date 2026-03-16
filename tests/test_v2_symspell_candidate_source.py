from __future__ import annotations

from pathlib import Path

from app.core.v2 import SymSpellCandidateSource


def _write_dictionary(path: Path) -> None:
    path.write_text("дилемму 100\nдом 50\n", encoding="utf-8")


def test_symspell_candidate_source_returns_expected_candidate(tmp_path: Path) -> None:
    dictionary = tmp_path / "tiny_dict.txt"
    _write_dictionary(dictionary)

    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)
    candidates = source.candidates_for_token("делемму")

    tokens = {row.token for row in candidates}
    assert "дилемму" in tokens


def test_symspell_candidate_source_respects_max_candidates(tmp_path: Path) -> None:
    dictionary = tmp_path / "tiny_dict.txt"
    _write_dictionary(dictionary)

    source = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=1, include_original=True)
    candidates = source.candidates_for_token("делемму")

    assert len(candidates) == 1


def test_symspell_candidate_source_original_token_toggle(tmp_path: Path) -> None:
    dictionary = tmp_path / "tiny_dict.txt"
    _write_dictionary(dictionary)

    with_original = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=True)
    without_original = SymSpellCandidateSource(dictionary_path=dictionary, max_candidates=5, include_original=False)

    tokens_with = {row.token for row in with_original.candidates_for_token("абракадабра")}
    tokens_without = {row.token for row in without_original.candidates_for_token("абракадабра")}

    assert "абракадабра" in tokens_with
    assert "абракадабра" not in tokens_without
