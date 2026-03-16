from __future__ import annotations

from pathlib import Path

import pytest

from tests.prepare_v2_kenlm_model import build_local_kenlm_model, load_corpus_texts


def test_load_corpus_texts_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        load_corpus_texts(missing)


def test_load_corpus_texts_rejects_empty_file(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.txt"
    corpus.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="corpus is empty"):
        load_corpus_texts(corpus)


def test_build_local_kenlm_model_writes_arpa(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("сегодня будет встреча\nэто тест\n", encoding="utf-8")
    out = tmp_path / "model.arpa"

    built = build_local_kenlm_model(corpus_path=corpus, output_path=out)

    assert built == out
    assert built.exists()
    text = built.read_text(encoding="utf-8")
    assert "\\data\\" in text
    assert "\\1-grams:" in text
    assert "\\2-grams:" in text
    assert "\\end\\" in text
