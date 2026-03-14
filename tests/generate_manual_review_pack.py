"""Generate compact high-signal manual review pack from existing evaluation sources."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
from tests import eval_candidate_harness, eval_ruspellgold_harness

DEFAULT_OUTPUT_JSONL = Path("manual_review_pack.jsonl")
DEFAULT_OUTPUT_MD = Path("manual_review_pack.md")
DEFAULT_CONFIG_PATH = Path("config.smart_baseline_staging.yml")
DEFAULT_PRODUCT_CASES_PATH = Path("tests/cases/product_regression_user_texts.yml")

REVIEW_REASON_ORDER: tuple[str, ...] = (
    "rollback_related",
    "candidate_rejected_unsafe",
    "candidate_ambiguous",
    "candidate_generated_not_applied",
    "expected_mismatch",
    "user_visible_change",
    "protected_context_case",
    "complex_user_like",
)
REVIEW_REASON_SET = set(REVIEW_REASON_ORDER)

RISK_REASONS: tuple[str, ...] = (
    "rollback_related",
    "candidate_rejected_unsafe",
    "candidate_ambiguous",
    "expected_mismatch",
    "protected_context_case",
)
EXPECTED_IMPROVEMENT_REASONS: tuple[str, ...] = (
    "candidate_generated_not_applied",
    "user_visible_change",
    "complex_user_like",
)


@dataclass(frozen=True)
class ReviewInputCase:
    input_text: str
    expected_clean_text: str | None
    source: str
    category: str | None


@dataclass(frozen=True)
class ReviewOutcome:
    input_text: str
    output_text: str
    expected_clean_text: str | None
    source: str
    category: str | None
    reasons: tuple[str, ...]
    stats: dict[str, int | bool]


# Reuse the same value taxonomy as delta report utility to keep interpretation stable.
DELTA_REASON_SET: tuple[str, ...] = (
    "smart_improves_expected_match",
    "smart_regresses_expected_match",
    "both_match_expected_but_different_output",
    "profile_outputs_differ_need_human_review",
)


def _load_product_cases(path: Path) -> tuple[ReviewInputCase, ...]:
    if not path.exists():
        return ()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ()

    items = payload.get("smart")
    if not isinstance(items, list):
        return ()

    out: list[ReviewInputCase] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        input_text = row.get("input")
        expected = row.get("expected_clean_text")
        category = row.get("category")
        if isinstance(input_text, str) and isinstance(expected, str):
            out.append(
                ReviewInputCase(
                    input_text=input_text,
                    expected_clean_text=expected,
                    source="product_regression_pack",
                    category=category if isinstance(category, str) else None,
                )
            )
    return tuple(out)


def _load_cases_from_jsonl(path: Path) -> tuple[ReviewInputCase, ...]:
    cases: list[ReviewInputCase] = []
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid jsonl row type at line {index}")

        input_text = payload.get("input_text")
        expected = payload.get("expected_clean_text")
        source = payload.get("source", "custom_jsonl")
        category = payload.get("category")

        if not isinstance(input_text, str) or not input_text:
            raise ValueError(f"invalid input_text at line {index}")
        if expected is not None and not isinstance(expected, str):
            raise ValueError(f"invalid expected_clean_text at line {index}")
        if not isinstance(source, str):
            raise ValueError(f"invalid source at line {index}")
        if category is not None and not isinstance(category, str):
            raise ValueError(f"invalid category at line {index}")

        cases.append(
            ReviewInputCase(
                input_text=input_text,
                expected_clean_text=expected,
                source=source,
                category=category,
            )
        )

    if not cases:
        raise ValueError("source jsonl is empty")
    return tuple(cases)


def _load_default_cases(product_cases_path: Path) -> tuple[ReviewInputCase, ...]:
    cases: list[ReviewInputCase] = []

    for case in eval_candidate_harness.FIXED_RU_CASES:
        cases.append(
            ReviewInputCase(
                input_text=case.input_text,
                expected_clean_text=case.expected_clean_text,
                source="internal_eval_fixed",
                category="candidate_eval",
            )
        )

    for case in eval_ruspellgold_harness._load_benchmark_cases():
        cases.append(
            ReviewInputCase(
                input_text=case.input_text,
                expected_clean_text=case.expected_clean_text,
                source="external_benchmark",
                category="ruspellgold",
            )
        )

    cases.extend(_load_product_cases(product_cases_path))

    dedup: dict[tuple[str, str | None], ReviewInputCase] = {}
    for case in cases:
        key = (case.input_text, case.expected_clean_text)
        dedup.setdefault(key, case)

    return tuple(dedup.values())


def _extract_reasons(case: ReviewInputCase, output_text: str, stats: dict[str, int | bool]) -> tuple[str, ...]:
    reasons: list[str] = []
    if bool(stats.get("rollback_applied", False)):
        reasons.append("rollback_related")
    if int(stats.get("candidate_rejected_unsafe_candidate_count", 0)) > 0:
        reasons.append("candidate_rejected_unsafe")
    if int(stats.get("candidate_ambiguous_count", 0)) > 0 or int(stats.get("candidate_ambiguous_tie_count", 0)) > 0:
        reasons.append("candidate_ambiguous")
    if int(stats.get("candidate_generated_count", 0)) > 0 and int(stats.get("candidate_applied_count", 0)) == 0:
        reasons.append("candidate_generated_not_applied")
    if output_text != case.input_text:
        reasons.append("user_visible_change")
    if case.expected_clean_text is not None and output_text != case.expected_clean_text:
        reasons.append("expected_mismatch")
    if case.source == "product_regression_pack" and case.category in {"protected zones", "wrapped/no-touch"}:
        reasons.append("protected_context_case")
        reasons.append("complex_user_like")

    if not reasons:
        return ()

    unique = {r for r in reasons if r in REVIEW_REASON_SET}
    return tuple(r for r in REVIEW_REASON_ORDER if r in unique)


def _evaluate_cases(cases: tuple[ReviewInputCase, ...]) -> tuple[ReviewOutcome, ...]:
    outcomes: list[ReviewOutcome] = []
    for index, case in enumerate(cases, start=1):
        orchestrator = Orchestrator(correlation_id=f"manual-review-pack-{index}")
        with contextlib.redirect_stdout(io.StringIO()):
            output_text = orchestrator.clean(case.input_text, mode="smart")

        stats_raw = orchestrator.last_run_stats
        stats: dict[str, int | bool] = {
            "rollback_applied": bool(stats_raw.get("rollback_applied", False)),
            "candidate_generated_count": int(stats_raw.get("candidate_generated_count", 0)),
            "candidate_applied_count": int(stats_raw.get("candidate_applied_count", 0)),
            "candidate_rejected_unsafe_candidate_count": int(stats_raw.get("candidate_rejected_unsafe_candidate_count", 0)),
            "candidate_ambiguous_count": int(stats_raw.get("candidate_ambiguous_count", 0)),
            "candidate_ambiguous_tie_count": int(stats_raw.get("candidate_ambiguous_tie_count", 0)),
        }
        reasons = _extract_reasons(case, output_text, stats)
        if not reasons:
            continue

        outcomes.append(
            ReviewOutcome(
                input_text=case.input_text,
                output_text=output_text,
                expected_clean_text=case.expected_clean_text,
                source=case.source,
                category=case.category,
                reasons=reasons,
                stats=stats,
            )
        )

    return tuple(outcomes)


def _priority(outcome: ReviewOutcome) -> tuple[int, int]:
    reason_order = {reason: idx for idx, reason in enumerate(REVIEW_REASON_ORDER)}
    top = min(reason_order[r] for r in outcome.reasons)
    return (top, len(outcome.input_text))


def _read_json_if_exists(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def build_manual_review_pack(
    output_jsonl: Path,
    output_md: Path,
    config_path: Path,
    limit: int,
    source_jsonl: Path | None = None,
    product_cases_path: Path = DEFAULT_PRODUCT_CASES_PATH,
    eval_candidate_stats_path: Path | None = None,
    eval_benchmark_stats_path: Path | None = None,
) -> dict[str, int]:
    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(config_path)
    reset_app_config_cache()

    try:
        if source_jsonl is not None:
            cases = _load_cases_from_jsonl(source_jsonl)
        else:
            cases = _load_default_cases(product_cases_path)

        outcomes = list(_evaluate_cases(cases))
        outcomes.sort(key=_priority)
        selected = outcomes[:limit]

        reason_counts = {reason: 0 for reason in REVIEW_REASON_ORDER}
        for item in selected:
            for reason in item.reasons:
                reason_counts[reason] += 1

        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        output_md.parent.mkdir(parents=True, exist_ok=True)

        with output_jsonl.open("w", encoding="utf-8") as fh:
            for item in selected:
                payload = {
                    "input_text": item.input_text,
                    "output_text": item.output_text,
                    "expected_clean_text": item.expected_clean_text,
                    "primary_reason": item.reasons[0],
                    "secondary_reasons": list(item.reasons[1:]),
                    "why_in_pack": list(item.reasons),
                    "source": item.source,
                    "category": item.category,
                    "stats": item.stats,
                }
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

        cand_stats = _read_json_if_exists(eval_candidate_stats_path)
        bench_stats = _read_json_if_exists(eval_benchmark_stats_path)

        lines = [
            "# Manual Review Pack",
            "",
            f"- config: `{config_path}`",
            f"- total_candidates_scanned: {len(cases)}",
            f"- selected_high_signal_cases: {len(selected)}",
            "",
            "## Review taxonomy (stable reason buckets)",
            "",
            "Risk-oriented buckets:",
            *[f"- {reason}" for reason in RISK_REASONS],
            "",
            "Expected smart-improvement / usefulness buckets:",
            *[f"- {reason}" for reason in EXPECTED_IMPROVEMENT_REASONS],
            "",
            "Delta-report reason alignment (reference values):",
            *[f"- {reason}" for reason in DELTA_REASON_SET],
            "",
            "## Counts per reason",
            "",
        ]
        for reason in REVIEW_REASON_ORDER:
            lines.append(f"- {reason}: {reason_counts[reason]}")
        lines.append("")

        if cand_stats is not None or bench_stats is not None:
            lines.extend(["## Aggregated context", ""])
            if cand_stats is not None:
                lines.append(f"- internal_eval_stats_present: yes (keys={len(cand_stats)})")
            else:
                lines.append("- internal_eval_stats_present: no")
            if bench_stats is not None:
                lines.append(f"- external_benchmark_stats_present: yes (keys={len(bench_stats)})")
            else:
                lines.append("- external_benchmark_stats_present: no")
            lines.append("")

        lines.extend(["## Cases", ""])
        for index, item in enumerate(selected, start=1):
            lines.extend(
                [
                    f"### Case {index}",
                    f"- source: `{item.source}`",
                    f"- category: `{item.category}`" if item.category else "- category: _not provided_",
                    f"- primary_reason: `{item.reasons[0]}`",
                    f"- secondary_reasons: `{', '.join(item.reasons[1:])}`" if len(item.reasons) > 1 else "- secondary_reasons: _none_",
                    f"- why_in_pack: `{', '.join(item.reasons)}`",
                    "- input_text:",
                    f"  - {item.input_text}",
                    "- output_text:",
                    f"  - {item.output_text}",
                    f"- expected_clean_text: `{item.expected_clean_text}`" if item.expected_clean_text is not None else "- expected_clean_text: _not provided_",
                    "",
                ]
            )

        output_md.write_text("\n".join(lines), encoding="utf-8")
        return {
            "total_candidates_scanned": len(cases),
            "selected_high_signal_cases": len(selected),
        }
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate compact manual review pack from existing eval/benchmark sources")
    parser.add_argument("--output-jsonl", default=str(DEFAULT_OUTPUT_JSONL), help="Path to output JSONL review pack")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Path to output markdown summary")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="YAML config used for smart-mode evaluation")
    parser.add_argument("--limit", type=int, default=40, help="Maximum number of selected high-signal cases")
    parser.add_argument("--source-jsonl", default=None, help="Optional custom source JSONL with input_text/expected_clean_text")
    parser.add_argument(
        "--product-cases",
        default=str(DEFAULT_PRODUCT_CASES_PATH),
        help="Path to product regression YAML (used when --source-jsonl is not provided)",
    )
    parser.add_argument("--eval-candidate-stats", default=None, help="Optional path to eval_candidate_harness JSON artifact")
    parser.add_argument("--eval-benchmark-stats", default=None, help="Optional path to eval_ruspellgold_harness JSON artifact")
    args = parser.parse_args()

    summary = build_manual_review_pack(
        output_jsonl=Path(args.output_jsonl),
        output_md=Path(args.output_md),
        config_path=Path(args.config),
        limit=args.limit,
        source_jsonl=Path(args.source_jsonl) if args.source_jsonl else None,
        product_cases_path=Path(args.product_cases),
        eval_candidate_stats_path=Path(args.eval_candidate_stats) if args.eval_candidate_stats else None,
        eval_benchmark_stats_path=Path(args.eval_benchmark_stats) if args.eval_benchmark_stats else None,
    )

    print(
        "manual review pack summary: "
        f"total_candidates_scanned={summary['total_candidates_scanned']}, "
        f"selected_high_signal_cases={summary['selected_high_signal_cases']}, "
        f"output_jsonl={args.output_jsonl}, "
        f"output_md={args.output_md}"
    )


if __name__ == "__main__":
    main()
