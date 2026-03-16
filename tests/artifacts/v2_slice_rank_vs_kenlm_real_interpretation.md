# RankBasedScorer vs KenLMScorer (curated slice)

- dataset: `tests/cases/v2_token_replay_slice_a.jsonl`
- result: KenLM run completed.
- expected_match_count_delta: 0
- expected_match_rate_delta: 0.0
- expected_match_when_changed_rate_delta: 0.0
- changed_count_delta: 0
- decision_reason_counts_delta: {'low_confidence': 10, 'original_wins': -10}

Interpretation: on this tiny corpus/model, aggregate match metrics remained unchanged; only decision-reason distribution shifted.