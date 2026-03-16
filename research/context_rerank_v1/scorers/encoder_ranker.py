from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from .base import SentenceCandidateScorer


def encoder_backend_available() -> bool:
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("transformers") is not None


class EncoderRankerScorer(SentenceCandidateScorer):
    """Research-only encoder scorer for candidate reranking.

    Uses a masked-LM style score when possible; falls back to sentence pseudo-logprob.
    This scorer is offline-only and not connected to production runtime.
    """

    def __init__(
        self,
        model_name_or_path: str,
        *,
        batch_size: int = 8,
        max_seq_len: int = 128,
        device: str = "cpu",
        cache_dir: str | None = None,
        local_files_only: bool = False,
    ) -> None:
        if not encoder_backend_available():
            raise RuntimeError("encoder_ranker backend is not available (requires torch and transformers)")

        import torch  # type: ignore
        from transformers import AutoModelForMaskedLM, AutoTokenizer  # type: ignore

        self._torch = torch
        self._batch_size = max(1, int(batch_size))
        self._max_seq_len = max(8, int(max_seq_len))
        self._device = device

        model_arg: str | Path = model_name_or_path
        path = Path(model_name_or_path)
        if path.exists():
            model_arg = path

        self._tokenizer = AutoTokenizer.from_pretrained(
            str(model_arg),
            cache_dir=cache_dir,
            local_files_only=local_files_only,
        )
        self._model = AutoModelForMaskedLM.from_pretrained(
            str(model_arg),
            cache_dir=cache_dir,
            local_files_only=local_files_only,
        )
        self._model.eval()
        self._model.to(self._device)

    def score(self, tokens: tuple[str, ...], position: int, candidate: str) -> float:
        if position < 0 or position >= len(tokens):
            raise IndexError("position out of range")

        replaced = list(tokens)
        replaced[position] = candidate
        replaced_text = " ".join(replaced)

        mask_token = getattr(self._tokenizer, "mask_token", None)
        if not mask_token:
            return self._score_sentence(replaced_text)

        masked = list(tokens)
        masked[position] = mask_token
        masked_text = " ".join(masked)

        enc = self._tokenizer(
            masked_text,
            return_tensors="pt",
            truncation=True,
            max_length=self._max_seq_len,
        )
        enc = {k: v.to(self._device) for k, v in enc.items()}
        mask_id = getattr(self._tokenizer, "mask_token_id", None)
        if mask_id is None:
            return self._score_sentence(replaced_text)

        mask_positions = (enc["input_ids"][0] == mask_id).nonzero(as_tuple=False)
        if mask_positions.numel() == 0:
            return self._score_sentence(replaced_text)

        cand_ids = self._tokenizer(candidate, add_special_tokens=False)["input_ids"]
        if len(cand_ids) != 1:
            return self._score_sentence(replaced_text)

        with self._torch.no_grad():
            out = self._model(**enc)
            logits = out.logits[0, int(mask_positions[0].item())]
            log_probs = self._torch.log_softmax(logits, dim=-1)
            return float(log_probs[cand_ids[0]].item())

    def score_sentence(self, tokens: tuple[str, ...], eos: bool = True) -> float:
        del eos
        return self._score_sentence(" ".join(tokens))

    def _score_sentence(self, text: str) -> float:
        enc = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self._max_seq_len,
        )
        enc = {k: v.to(self._device) for k, v in enc.items()}
        labels = enc["input_ids"].clone()

        with self._torch.no_grad():
            out = self._model(**enc, labels=labels)
            # Negative token-normalized loss as pseudo log-prob proxy.
            loss = float(out.loss.item())
            token_count = int(labels.shape[1]) if labels.ndim == 2 else 1
            return -loss * max(1, token_count)
