from __future__ import annotations

from app.core.orchestrator import Orchestrator
from app.core.v2 import CandidateOption, SelectorContext, make_v2_selector_scaffold


class _StubScorer:
    def __init__(self, table: dict[str, float]) -> None:
        self._table = table

    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return self._table.get(candidate.token, 0.0)


def test_v2_scaffold_import_and_init() -> None:
    scaffold = make_v2_selector_scaffold(min_confidence=0.1, min_margin=0.2)
    assert scaffold.decision.min_confidence == 0.1
    assert scaffold.decision.min_margin == 0.2


def test_v2_selector_fail_closed_no_candidate() -> None:
    scaffold = make_v2_selector_scaffold()
    decision = scaffold.evaluate_token(
        context=SelectorContext(left_context=("в",), original_token="севодня", right_context=("будет",)),
        candidates=tuple(),
        scorer=_StubScorer({}),
    )
    assert decision.changed is False
    assert decision.reason == "no_candidate"
    assert decision.selected_token == "севодня"


def test_v2_selector_fail_closed_low_margin() -> None:
    scaffold = make_v2_selector_scaffold(min_confidence=0.0, min_margin=0.5)
    decision = scaffold.evaluate_token(
        context=SelectorContext(left_context=("в",), original_token="севодня", right_context=("будет",)),
        candidates=(CandidateOption("сегодня", 0), CandidateOption("севодня", 1)),
        scorer=_StubScorer({"сегодня": 0.2, "севодня": 0.0}),
    )
    assert decision.changed is False
    assert decision.reason == "low_margin"


def test_v2_selector_can_apply_candidate_when_confident() -> None:
    scaffold = make_v2_selector_scaffold(min_confidence=0.1, min_margin=0.05)
    decision = scaffold.evaluate_token(
        context=SelectorContext(left_context=("в",), original_token="севодня", right_context=("будет",)),
        candidates=(CandidateOption("сегодня", 0), CandidateOption("севодня", 1)),
        scorer=_StubScorer({"сегодня": 0.7, "севодня": 0.1}),
    )
    assert decision.changed is True
    assert decision.reason == "apply_candidate"
    assert decision.selected_token == "сегодня"


def test_baseline_orchestrator_coexists_with_v2_scaffold_disabled_by_default() -> None:
    orchestrator = Orchestrator(correlation_id="v2-scaffold-test")
    out = orchestrator.clean("привет ,как дела ?", mode="smart")
    assert isinstance(out, str)
    assert orchestrator.last_run_stats["v2_selector_scaffold_enabled"] is False
    assert orchestrator.last_run_stats["v2_selector_scaffold_available"] is False
