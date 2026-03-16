"""Prepare a tiny local KenLM ARPA model for V2 offline scorer comparison.

This utility is offline/dev-only and writes to a user-provided output path.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research.context_rerank_v1.scorers.kenlm import KenLMScorer

DEFAULT_OUTPUT_PATH = Path("tests/artifacts/local_v2_kenlm_model.arpa")


def load_corpus_texts(path: Path) -> tuple[str, ...]:
    if not path.exists():
        raise FileNotFoundError(f"corpus file not found: {path}")
    rows = tuple(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if not rows:
        raise ValueError(f"corpus is empty: {path}")
    return rows


def build_local_kenlm_model(*, corpus_path: Path, output_path: Path) -> Path:
    corpus = load_corpus_texts(corpus_path)
    return KenLMScorer.train_bigram_arpa(corpus_texts=corpus, output_path=output_path)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build tiny local KenLM ARPA model for V2 scorer runner")
    p.add_argument("--corpus", required=True, help="Path to plain-text corpus (one sentence per line)")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Path to output ARPA model")
    return p


def main() -> None:
    args = _parser().parse_args()
    out = build_local_kenlm_model(corpus_path=Path(args.corpus), output_path=Path(args.output))
    print(f"prepared_kenlm_model={out}")


if __name__ == "__main__":
    main()
