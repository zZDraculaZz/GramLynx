from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
import re

from .base import SentenceCandidateScorer

TOKEN_RE = re.compile(r"\b[\w-]+\b", flags=re.UNICODE)


class KenLMScorer(SentenceCandidateScorer):
    """Sentence-level KenLM scorer for offline research replay.

    Requires `kenlm` python package and an ARPA model path.
    """

    def __init__(self, model_path: str | Path) -> None:
        try:
            import kenlm  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("kenlm backend is not available") from exc

        self._model_path = Path(model_path)
        if not self._model_path.exists():
            raise FileNotFoundError(f"kenlm model not found: {self._model_path}")
        self._model = kenlm.Model(str(self._model_path))

    def score(self, tokens: tuple[str, ...], position: int, candidate: str) -> float:
        if position < 0 or position >= len(tokens):
            raise IndexError("position out of range")
        replaced = list(tokens)
        replaced[position] = candidate
        return self.score_sentence(tuple(replaced), eos=True)

    def score_sentence(self, tokens: tuple[str, ...], eos: bool = True) -> float:
        sentence = " ".join(tokens)
        return float(self._model.score(sentence, bos=True, eos=eos))

    @staticmethod
    def train_bigram_arpa(corpus_texts: tuple[str, ...], output_path: str | Path) -> Path:
        """Train a small deterministic bigram ARPA model from plain texts."""
        out = Path(output_path)
        tokenized: list[list[str]] = [TOKEN_RE.findall(text.lower()) for text in corpus_texts]
        tokenized = [tokens for tokens in tokenized if tokens]
        if not tokenized:
            raise ValueError("cannot train kenlm model on empty corpus")

        unigram = Counter()
        bigram = Counter()
        prev_totals = Counter()

        for sent in tokenized:
            chain = ["<s>", *sent, "</s>"]
            for token in chain:
                unigram[token] += 1
            for left, right in zip(chain, chain[1:]):
                bigram[(left, right)] += 1
                prev_totals[left] += 1

        vocab = sorted(unigram.keys())
        if "<unk>" not in vocab:
            vocab.insert(0, "<unk>")

        vocab_size = len(vocab)
        total_unigrams = sum(unigram.values()) + vocab_size

        lines = ["\\data\\", f"ngram 1={len(vocab)}", f"ngram 2={len(bigram)}", "", "\\1-grams:"]
        for token in vocab:
            count = unigram.get(token, 0)
            prob = (count + 1) / total_unigrams
            log_prob = math.log10(prob)
            backoff = math.log10(0.4)
            lines.append(f"{log_prob:.7f}\t{token}\t{backoff:.7f}")

        lines.extend(["", "\\2-grams:"])
        for (left, right), count in sorted(bigram.items()):
            prob = (count + 1) / (prev_totals[left] + vocab_size)
            log_prob = math.log10(prob)
            lines.append(f"{log_prob:.7f}\t{left} {right}")

        lines.extend(["", "\\end\\"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
