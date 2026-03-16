from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence
from pathlib import Path

import yaml

from .candidate_sources import SymSpellCandidateSource
from .interfaces import CandidateOption, CandidateScorer, SelectorContext
from .scaffold import make_v2_selector_scaffold


@dataclass(frozen=True)
class ReplayFixtureCase:
    case_id: str
    context: SelectorContext
    candidates: tuple[CandidateOption, ...]
    scores: dict[str, float]
    expected_token: str


@dataclass(frozen=True)
class ReplayCaseResult:
    case_id: str
    selected_token: str
    expected_token: str
    reason: str
    changed: bool


@dataclass(frozen=True)
class TextCleanCase:
    input_text: str
    expected_clean_text: str
    left_context: tuple[str, ...] = tuple()
    right_context: tuple[str, ...] = tuple()


class _TableScorer:
    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return float(self._scores.get(candidate.token, 0.0))




class RankBasedScorer:
    """Small deterministic scorer for offline shortlist replay.

    Scores candidate by its shortlist rank value only.
    """

    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return float(candidate.rank)
def load_text_clean_jsonl(
    path: Path,
    *,
    allow_input_alias: bool = False,
    require_non_empty_input: bool = True,
) -> tuple[TextCleanCase, ...]:
    rows: list[TextCleanCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid row type at line {line_no}")

        input_text = payload.get("input_text")
        if allow_input_alias and not isinstance(input_text, str):
            input_text = payload.get("input")
        expected_clean_text = payload.get("expected_clean_text")
        left_context = payload.get("left_context", [])
        right_context = payload.get("right_context", [])
        if not isinstance(input_text, str) or not isinstance(expected_clean_text, str):
            raise ValueError(f"invalid schema at line {line_no}")
        if not isinstance(left_context, list) or not all(isinstance(x, str) for x in left_context):
            raise ValueError(f"invalid schema at line {line_no}")
        if not isinstance(right_context, list) or not all(isinstance(x, str) for x in right_context):
            raise ValueError(f"invalid schema at line {line_no}")
        if require_non_empty_input and not input_text:
            raise ValueError(f"invalid schema at line {line_no}")
        rows.append(
            TextCleanCase(
                input_text=input_text,
                expected_clean_text=expected_clean_text,
                left_context=tuple(left_context),
                right_context=tuple(right_context),
            )
        )

    if not rows:
        raise ValueError(f"empty dataset: {path}")
    return tuple(rows)


def load_text_clean_yaml_smart(path: Path) -> tuple[TextCleanCase, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid yaml corpus schema")
    smart_rows = payload.get("smart")
    if not isinstance(smart_rows, list):
        raise ValueError("invalid yaml corpus schema: smart list missing")

    rows: list[TextCleanCase] = []
    for index, row in enumerate(smart_rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"invalid yaml row at index {index}")
        input_text = row.get("input")
        expected_clean_text = row.get("expected_clean_text")
        left_context = row.get("left_context", [])
        right_context = row.get("right_context", [])
        if not isinstance(input_text, str) or not isinstance(expected_clean_text, str):
            raise ValueError(f"invalid yaml row schema at index {index}")
        if not isinstance(left_context, list) or not all(isinstance(x, str) for x in left_context):
            raise ValueError(f"invalid yaml row schema at index {index}")
        if not isinstance(right_context, list) or not all(isinstance(x, str) for x in right_context):
            raise ValueError(f"invalid yaml row schema at index {index}")
        rows.append(
            TextCleanCase(
                input_text=input_text,
                expected_clean_text=expected_clean_text,
                left_context=tuple(left_context),
                right_context=tuple(right_context),
            )
        )

    return tuple(rows)


def load_text_clean_cases(path: Path) -> tuple[TextCleanCase, ...]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return load_text_clean_jsonl(path, allow_input_alias=True, require_non_empty_input=False)
    if suffix in {".yml", ".yaml"}:
        return load_text_clean_yaml_smart(path)
    raise ValueError(f"unsupported dataset format: {path}")


def load_replay_cases(path: Path) -> tuple[ReplayFixtureCase, ...]:
    rows: list[ReplayFixtureCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid row type at line {line_no}")

        case_id = payload.get("case_id")
        original_token = payload.get("original_token")
        expected_token = payload.get("expected_token")
        left_context = payload.get("left_context")
        right_context = payload.get("right_context")
        candidates = payload.get("candidates")
        scores = payload.get("scores")

        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"invalid case_id at line {line_no}")
        if not isinstance(original_token, str) or not original_token:
            raise ValueError(f"invalid original_token at line {line_no}")
        if not isinstance(expected_token, str) or not expected_token:
            raise ValueError(f"invalid expected_token at line {line_no}")
        if not isinstance(left_context, list) or not all(isinstance(t, str) for t in left_context):
            raise ValueError(f"invalid left_context at line {line_no}")
        if not isinstance(right_context, list) or not all(isinstance(t, str) for t in right_context):
            raise ValueError(f"invalid right_context at line {line_no}")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(f"invalid candidates at line {line_no}")
        if not isinstance(scores, dict) or not all(isinstance(k, str) for k in scores):
            raise ValueError(f"invalid scores at line {line_no}")

        candidate_rows: list[CandidateOption] = []
        for c in candidates:
            if not isinstance(c, dict):
                raise ValueError(f"invalid candidate row at line {line_no}")
            token = c.get("token")
            rank = c.get("rank", 0)
            if not isinstance(token, str) or not token:
                raise ValueError(f"invalid candidate token at line {line_no}")
            if not isinstance(rank, int):
                raise ValueError(f"invalid candidate rank at line {line_no}")
            candidate_rows.append(CandidateOption(token=token, rank=rank))

        rows.append(
            ReplayFixtureCase(
                case_id=case_id,
                context=SelectorContext(
                    left_context=tuple(left_context),
                    original_token=original_token,
                    right_context=tuple(right_context),
                ),
                candidates=tuple(candidate_rows),
                scores={k: float(v) for k, v in scores.items()},
                expected_token=expected_token,
            )
        )

    if not rows:
        raise ValueError(f"empty dataset: {path}")
    return tuple(rows)


def replay_cases(
    cases: tuple[ReplayFixtureCase, ...],
    *,
    min_confidence: float = 0.0,
    min_margin: float = 0.0,
) -> tuple[ReplayCaseResult, ...]:
    scaffold = make_v2_selector_scaffold(min_confidence=min_confidence, min_margin=min_margin)
    outcomes: list[ReplayCaseResult] = []
    for case in cases:
        decision = scaffold.evaluate_token(
            context=case.context,
            candidates=case.candidates,
            scorer=_TableScorer(case.scores),
        )
        outcomes.append(
            ReplayCaseResult(
                case_id=case.case_id,
                selected_token=decision.selected_token,
                expected_token=case.expected_token,
                reason=decision.reason,
                changed=decision.changed,
            )
        )
    return tuple(outcomes)




def run_symspell_selector_replay(
    cases: Sequence[TextCleanCase],
    *,
    symspell_source: SymSpellCandidateSource,
    scorer: CandidateScorer,
    max_candidates: int = 5,
    min_confidence: float = 0.0,
    min_margin: float = 0.0,
) -> dict[str, int | float]:
    if max_candidates < 1:
        raise ValueError("max_candidates must be >= 1")

    scaffold = make_v2_selector_scaffold(min_confidence=min_confidence, min_margin=min_margin)
    outcomes: list[ReplayCaseResult] = []

    for index, case in enumerate(cases, start=1):
        token = case.input_text.strip()
        expected_token = case.expected_clean_text.strip()
        if not token or not expected_token:
            raise ValueError(f"invalid token replay case at index {index}")

        candidates = list(symspell_source.candidates_for_token(token))
        if not any(c.token == token for c in candidates):
            candidates.append(CandidateOption(token=token, rank=0))
        candidates = candidates[:max_candidates]

        decision = scaffold.evaluate_token(
            context=SelectorContext(left_context=case.left_context, original_token=token, right_context=case.right_context),
            candidates=tuple(candidates),
            scorer=scorer,
        )
        outcomes.append(
            ReplayCaseResult(
                case_id=f"symspell-{index}",
                selected_token=decision.selected_token,
                expected_token=expected_token,
                reason=decision.reason,
                changed=decision.changed,
            )
        )

    return summarize_replay(tuple(outcomes))
def summarize_replay(results: tuple[ReplayCaseResult, ...]) -> dict[str, int | float]:
    total = len(results)
    exact = sum(1 for row in results if row.selected_token == row.expected_token)
    changed = tuple(row for row in results if row.changed)
    changed_exact = sum(1 for row in changed if row.selected_token == row.expected_token)

    reason_counts: dict[str, int] = {}
    for row in results:
        reason_counts[row.reason] = reason_counts.get(row.reason, 0) + 1

    return {
        "total_cases": total,
        "expected_match_count": exact,
        "expected_match_rate": round(exact / total, 6) if total else 0.0,
        "changed_count": len(changed),
        "kept_original_count": total - len(changed),
        "expected_match_when_changed_count": changed_exact,
        "expected_match_when_changed_rate": round(changed_exact / len(changed), 6) if changed else 0.0,
        "decision_reason_counts": reason_counts,
    }


def compare_replay_summaries(
    baseline: dict[str, int | float | dict[str, int]],
    challenger: dict[str, int | float | dict[str, int]],
) -> dict[str, int | float | dict[str, int]]:
    def _num(summary: dict[str, int | float | dict[str, int]], key: str) -> float:
        value = summary.get(key, 0)
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    total_baseline = int(_num(baseline, "total_cases"))
    total_challenger = int(_num(challenger, "total_cases"))
    if total_baseline != total_challenger:
        raise ValueError("total_cases mismatch")

    base_reasons = baseline.get("decision_reason_counts", {})
    chal_reasons = challenger.get("decision_reason_counts", {})
    if not isinstance(base_reasons, dict):
        base_reasons = {}
    if not isinstance(chal_reasons, dict):
        chal_reasons = {}

    reason_deltas: dict[str, int] = {}
    for reason in sorted(set(base_reasons) | set(chal_reasons)):
        b = int(base_reasons.get(reason, 0))
        c = int(chal_reasons.get(reason, 0))
        reason_deltas[reason] = c - b

    return {
        "total_cases": total_baseline,
        "expected_match_count_delta": int(_num(challenger, "expected_match_count") - _num(baseline, "expected_match_count")),
        "expected_match_rate_delta": round(_num(challenger, "expected_match_rate") - _num(baseline, "expected_match_rate"), 6),
        "expected_match_when_changed_count_delta": int(
            _num(challenger, "expected_match_when_changed_count") - _num(baseline, "expected_match_when_changed_count")
        ),
        "expected_match_when_changed_rate_delta": round(
            _num(challenger, "expected_match_when_changed_rate") - _num(baseline, "expected_match_when_changed_rate"),
            6,
        ),
        "changed_count_delta": int(_num(challenger, "changed_count") - _num(baseline, "changed_count")),
        "kept_original_count_delta": int(_num(challenger, "kept_original_count") - _num(baseline, "kept_original_count")),
        "decision_reason_counts_delta": reason_deltas,
    }


def run_ab_replay_and_compare(
    cases: Sequence[TextCleanCase],
    *,
    symspell_source: SymSpellCandidateSource,
    scorer_a: CandidateScorer,
    scorer_b: CandidateScorer,
    max_candidates: int = 5,
    min_confidence: float = 0.0,
    min_margin: float = 0.0,
) -> dict[str, int | float | dict[str, int]]:
    summary_a = run_symspell_selector_replay(
        cases,
        symspell_source=symspell_source,
        scorer=scorer_a,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
        min_margin=min_margin,
    )
    summary_b = run_symspell_selector_replay(
        cases,
        symspell_source=symspell_source,
        scorer=scorer_b,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
        min_margin=min_margin,
    )
    return compare_replay_summaries(summary_a, summary_b)


def run_slice_scorer_comparison(
    cases_or_path: Sequence[TextCleanCase] | Path,
    *,
    symspell_source: SymSpellCandidateSource,
    scorer_a: CandidateScorer,
    scorer_b: CandidateScorer,
    max_candidates: int = 5,
    min_confidence: float = 0.0,
    min_margin: float = 0.0,
) -> dict[str, dict[str, int | float | dict[str, int]]]:
    """Run canonical scorer A/B comparison for a replay slice.

    Returns both per-scorer summaries plus the challenger-vs-baseline delta.
    """

    cases = load_text_clean_cases(cases_or_path) if isinstance(cases_or_path, Path) else tuple(cases_or_path)

    summary_a = run_symspell_selector_replay(
        cases,
        symspell_source=symspell_source,
        scorer=scorer_a,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
        min_margin=min_margin,
    )
    summary_b = run_symspell_selector_replay(
        cases,
        symspell_source=symspell_source,
        scorer=scorer_b,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
        min_margin=min_margin,
    )

    return {
        "summary_a": summary_a,
        "summary_b": summary_b,
        "delta": compare_replay_summaries(summary_a, summary_b),
    }
