# V2 slice scorer comparison (RankBasedScorer vs KenLMScorer)

Status: **blocked**

- Dataset: `tests/cases/v2_token_replay_slice_a.jsonl`
- KenLM backend available in current env: `false`
- Usable KenLM model path found: `false`

Blocking requirements:
1. Install Python `kenlm` backend in the active environment.
2. Provide a valid KenLM model file (`.arpa` or KenLM binary) and pass it to the runner (`--kenlm-model`).
