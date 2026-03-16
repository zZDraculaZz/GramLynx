"""Tiny offline runner: scorer comparison report on curated V2 token replay slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.v2 import CandidateOption, KenLMScorer, SelectorContext, SymSpellCandidateSource, is_kenlm_available
from app.core.v2.offline_eval import RankBasedScorer, run_slice_scorer_comparison

DEFAULT_SLICE_PATH = Path("tests/cases/v2_token_replay_slice_a.jsonl")
DEFAULT_OUTPUT_JSON = Path("v2_slice_scorer_comparison.json")


class ReverseRankScorer:
    """Deterministic challenger scorer for offline A/B slice checks."""

    def score_candidate(self, context: SelectorContext, candidate: CandidateOption) -> float:
        _ = context
        return -float(candidate.rank)


def _metrics_view(summary: dict[str, int | float | dict[str, int]]) -> dict[str, int | float]:
    keys = (
        "total_cases",
        "expected_match_count",
        "expected_match_rate",
        "changed_count",
        "kept_original_count",
        "expected_match_when_changed_count",
        "expected_match_when_changed_rate",
    )
    return {k: summary[k] for k in keys if k in summary and isinstance(summary[k], (int, float))}


def format_compact_report(
    payload: dict[str, dict[str, int | float | dict[str, int]]],
    *,
    challenger_name: str,
) -> str:
    summary_a = payload["summary_a"]
    summary_b = payload["summary_b"]
    delta = payload["delta"]

    total_cases = int(summary_a.get("total_cases", 0))

    lines = [
        "v2 slice scorer comparison summary:",
        "- baseline_scorer: RankBasedScorer",
        f"- challenger_scorer: {challenger_name}",
        f"- total_cases: {total_cases}",
        f"- summary_a: {_metrics_view(summary_a)}",
        f"- summary_b: {_metrics_view(summary_b)}",
        "- delta: "
        + str(
            {
                "expected_match_count_delta": delta.get("expected_match_count_delta", 0),
                "expected_match_rate_delta": delta.get("expected_match_rate_delta", 0.0),
                "changed_count_delta": delta.get("changed_count_delta", 0),
                "kept_original_count_delta": delta.get("kept_original_count_delta", 0),
                "expected_match_when_changed_count_delta": delta.get("expected_match_when_changed_count_delta", 0),
                "expected_match_when_changed_rate_delta": delta.get("expected_match_when_changed_rate_delta", 0.0),
            }
        ),
        f"- decision_reason_counts_delta: {delta.get('decision_reason_counts_delta', {})}",
    ]
    return "\n".join(lines)


def _resolve_challenger(*, mode: str, kenlm_model_path: Path | None) -> tuple[object, str]:
    if mode == "kenlm" and is_kenlm_available() and kenlm_model_path is not None and kenlm_model_path.exists():
        return KenLMScorer(kenlm_model_path), "KenLMScorer"
    return ReverseRankScorer(), "ReverseRankScorer"


def run_report(
    *,
    cases_path: Path,
    dictionary_path: Path,
    max_candidates: int,
    mode: str = "deterministic",
    kenlm_model_path: Path | None = None,
) -> tuple[dict[str, dict[str, int | float | dict[str, int]]], str]:
    source = SymSpellCandidateSource(dictionary_path=dictionary_path, max_candidates=max_candidates, include_original=True)
    scorer_b, challenger_name = _resolve_challenger(mode=mode, kenlm_model_path=kenlm_model_path)
    payload = run_slice_scorer_comparison(
        cases_path,
        symspell_source=source,
        scorer_a=RankBasedScorer(),
        scorer_b=scorer_b,
        max_candidates=max_candidates,
    )
    return payload, challenger_name


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run tiny v2 scorer comparison report on curated replay slice")
    p.add_argument("--cases", default=str(DEFAULT_SLICE_PATH), help="Path to text-clean replay slice (jsonl/yaml)")
    p.add_argument("--dictionary", required=True, help="Path to SymSpell dictionary text file")
    p.add_argument("--max-candidates", type=int, default=5)
    p.add_argument("--mode", choices=("deterministic", "kenlm"), default="deterministic")
    p.add_argument("--kenlm-model", default=None, help="Path to KenLM ARPA/binary model (for --mode kenlm)")
    p.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="Path to output JSON payload")
    return p


def main() -> None:
    args = _parser().parse_args()
    payload, challenger_name = run_report(
        cases_path=Path(args.cases),
        dictionary_path=Path(args.dictionary),
        max_candidates=int(args.max_candidates),
        mode=str(args.mode),
        kenlm_model_path=Path(args.kenlm_model) if args.kenlm_model else None,
    )

    Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_compact_report(payload, challenger_name=challenger_name))


if __name__ == "__main__":
    main()
