# Context-Aware Candidate Selection v1 (Offline Research Scaffold)

This directory contains a **research-only scaffold** for context-aware candidate selection.

## Scope
- This is **not** a production path.
- This scaffold is **not connected** to the main `/clean` runtime pipeline.
- It **does not** change API contract or runtime safe defaults.
- It exists only for offline replay/evaluation experiments.

## v1 design
- `candidate_source.py`: top-k candidate extraction from a large lexicon source.
- `scorers/base.py`: sentence-level scorer interface.
- `scorers/kenlm.py`: real KenLM-backed sentence scorer (`kenlm.Model`) + deterministic ARPA trainer helper.
- `decision.py`: fail-closed no-apply logic.
- `replay.py`: offline replay flow with mode comparison.
- `report.py`: aggregates and buckets for offline analysis.

## Compared modes
Replay computes comparable outputs for:
- `baseline` (keep original text)
- `current_apply` (runtime smart-mode output, used as reference)
- `research_replay_v1` (greedy per-token rerank, weaker baseline)
- `research_replay_v2` (combined base+KenLM score with beam search and fail-closed fallback)

## Leakage-safe KenLM setup
- Install research dependency: `pip install kenlm`.
- `scorer_type: kenlm` uses a real `kenlm.Model` sentence score.
- Scorer source **must be independent** from evaluation targets:
  - Option A (preferred in this step): `kenlm_model_path` -> external pre-trained ARPA model path/URL.
  - Option B: `kenlm_training_corpus_path` -> independent plain-text corpus.
- `replay.py` intentionally refuses eval-target self-training (no auto-training from `expected_clean_text` of eval set).

## Pretrained source used in examples
- External public source: `Lednik7/nto-ai-text-recognition`.
- Artifact URL: `https://raw.githubusercontent.com/Lednik7/nto-ai-text-recognition/main/models/nto_kenlm_model10.arpa`.
- The model is downloaded to local temp cache on first run when URL is provided.

## Included independent corpus (fallback research use)
- `resources/external_lm_corpus_ru.txt` provides a small independent corpus for deterministic offline experiments when prebuilt model is unavailable.

## Quick start
1. Use one of the example configs:
   - Pretrained full public: `research/context_rerank_v1/examples/full_public_pretrained.yaml`
   - Pretrained holdout: `research/context_rerank_v1/examples/product_holdout_pretrained.yaml`
   - Self-built baseline: `research/context_rerank_v1/examples/full_public_selfbuilt.yaml`
2. Run replay:
   - `python -m research.context_rerank_v1.replay --config research/context_rerank_v1/examples/full_public_pretrained.yaml --output-json research/context_rerank_v1/full_public_pretrained_report.json`


## CI note for research tests
- KenLM backend is optional in CI environments.
- Tests that require a real `kenlm` backend are skipped when the backend is unavailable.
- When `kenlm` is installed, those tests execute normally.

## KenLM v2 reranking
- Candidate score = weighted combination of base candidate score and KenLM sequence score.
- Search = beam search over sentence-level candidate sequences (`beam_width`).
- Reporting includes base/kenlm contribution sums and count of cases where beam search changed decision vs v1.
