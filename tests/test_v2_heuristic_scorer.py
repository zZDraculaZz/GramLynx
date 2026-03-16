from __future__ import annotations

from app.core.v2 import CandidateOption, ContextWindowHeuristicScorer, SelectorContext


def test_context_window_heuristic_scorer_is_deterministic_and_context_sensitive() -> None:
    scorer = ContextWindowHeuristicScorer()
    context = SelectorContext(left_context=("до",), original_token="завтро", right_context=("встречи",))

    good = scorer.score_candidate(context, CandidateOption(token="завтра", rank=1))
    bad = scorer.score_candidate(context, CandidateOption(token="завтро", rank=0))
    good_repeat = scorer.score_candidate(context, CandidateOption(token="завтра", rank=1))

    assert good > bad
    assert good == good_repeat
