"""Generate RuSpellGold tuning report for safe default vs smart baseline decisions."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import reset_app_config_cache  # noqa: E402
from app.core.orchestrator import Orchestrator  # noqa: E402
from tests import eval_ruspellgold_harness  # noqa: E402

DEFAULT_OUTPUT_MD = Path("ruspellgold_tuning_report.md")
DEFAULT_OUTPUT_JSON = Path("ruspellgold_tuning_report.json")
DEFAULT_SAFE_MODE = "baseline"
DEFAULT_SMART_MODE = "symspell_apply"
CANONICAL_COMMAND = (
    "python -m tests.report_ruspellgold_tuning --output-md ruspellgold_tuning_report.md "
    "--output-json ruspellgold_tuning_report.json"
)


def _mode_runtime(mode_label: str) -> tuple[bool, bool, str]:
    if mode_label == "baseline":
        return (False, False, "none")
    if mode_label == "rapidfuzz_shadow":
        return (True, True, "rapidfuzz")
    if mode_label == "rapidfuzz_apply":
        return (True, False, "rapidfuzz")
    if mode_label == "symspell_shadow":
        return (True, True, "symspell")
    if mode_label == "symspell_apply":
        return (True, False, "symspell")
    raise ValueError(f"unknown mode_label: {mode_label}")


def _wrong_invocation_hint() -> str | None:
    if __package__ in {None, ""}:
        return (
            "recommended invocation: run as module from repository root:\n"
            f"  {CANONICAL_COMMAND}"
        )
    return None


def _diagnose_runtime_error(exc: RuntimeError) -> str:
    message = str(exc)
    if "candidate backend unavailable" not in message:
        return message
    return (
        "RuSpellGold tuning report preflight failed (fail-closed): missing candidate backend dependency.\n"
        f"details: {message}\n"
        "required for full safe-vs-smart run: symspellpy and rapidfuzz\n"
        "install example: python -m pip install symspellpy rapidfuzz\n"
        "without full safe-vs-smart run, tuning changes must not be made."
    )


def _evaluate_cases_for_mode(mode_label: str) -> tuple[dict[str, float | int], list[dict[str, Any]]]:
    candidate_enabled, shadow_mode, backend = _mode_runtime(mode_label)
    eval_ruspellgold_harness._ensure_backend_available(backend)
    benchmark_cases = eval_ruspellgold_harness._load_benchmark_cases()
    dictionary_source = eval_ruspellgold_harness._resolve_eval_dictionary_source()

    cfg_path = Path(tempfile.gettempdir()) / f"gramlynx_ruspellgold_tuning_{mode_label}.yml"
    cfg_path.write_text(
        eval_ruspellgold_harness._runtime_config(candidate_enabled, shadow_mode, backend, dictionary_source),
        encoding="utf-8",
    )

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg_path)
    reset_app_config_cache()

    case_rows: list[dict[str, Any]] = []
    try:
        aggregates = {
            "candidate_generated_total": 0,
            "candidate_applied_total": 0,
            "candidate_rejected_total": 0,
            "candidate_rejected_no_result_total": 0,
            "candidate_rejected_unsafe_candidate_total": 0,
            "candidate_rejected_morph_blocked_total": 0,
            "candidate_rejected_morph_unknown_total": 0,
            "candidate_ambiguous_total": 0,
            "candidate_ambiguous_tie_total": 0,
            "candidate_shadow_skipped_total": 0,
            "rollback_total": 0,
            "exact_match_pass_count": 0,
        }

        for index, case in enumerate(benchmark_cases, start=1):
            orchestrator = Orchestrator(correlation_id=f"ruspellgold-tuning-{mode_label}-{index}")
            with contextlib.redirect_stdout(io.StringIO()):
                clean_text = orchestrator.clean(case.input_text, mode="smart")
            stats = orchestrator.last_run_stats

            expected_change = case.input_text != case.expected_clean_text
            case_exact_match = clean_text == case.expected_clean_text
            unchanged_when_expected_change = expected_change and clean_text == case.input_text
            wrong_change = clean_text != case.expected_clean_text and clean_text != case.input_text
            no_change_as_expected = (not expected_change) and clean_text == case.input_text

            row = {
                "case_id": index,
                "expected_change": expected_change,
                "exact_match": case_exact_match,
                "unchanged_when_expected_change": unchanged_when_expected_change,
                "wrong_change": wrong_change,
                "no_change_as_expected": no_change_as_expected,
                "candidate_generated_count": int(stats.get("candidate_generated_count", 0)),
                "candidate_applied_count": int(stats.get("candidate_applied_count", 0)),
                "candidate_rejected_count": int(stats.get("candidate_rejected_count", 0)),
                "candidate_rejected_no_result_count": int(stats.get("candidate_rejected_no_result_count", 0)),
                "candidate_rejected_unsafe_candidate_count": int(stats.get("candidate_rejected_unsafe_candidate_count", 0)),
                "candidate_rejected_morph_blocked_count": int(stats.get("candidate_rejected_morph_blocked_count", 0)),
                "candidate_rejected_morph_unknown_count": int(stats.get("candidate_rejected_morph_unknown_count", 0)),
                "candidate_ambiguous_count": int(stats.get("candidate_ambiguous_count", 0)),
                "candidate_ambiguous_tie_count": int(stats.get("candidate_ambiguous_tie_count", 0)),
                "candidate_shadow_skipped_count": int(stats.get("candidate_shadow_skipped_count", 0)),
                "rollback_applied": bool(stats.get("rollback_applied", False)),
            }

            aggregates["candidate_generated_total"] += row["candidate_generated_count"]
            aggregates["candidate_applied_total"] += row["candidate_applied_count"]
            aggregates["candidate_rejected_total"] += row["candidate_rejected_count"]
            aggregates["candidate_rejected_no_result_total"] += row["candidate_rejected_no_result_count"]
            aggregates["candidate_rejected_unsafe_candidate_total"] += row["candidate_rejected_unsafe_candidate_count"]
            aggregates["candidate_rejected_morph_blocked_total"] += row["candidate_rejected_morph_blocked_count"]
            aggregates["candidate_rejected_morph_unknown_total"] += row["candidate_rejected_morph_unknown_count"]
            aggregates["candidate_ambiguous_total"] += row["candidate_ambiguous_count"]
            aggregates["candidate_ambiguous_tie_total"] += row["candidate_ambiguous_tie_count"]
            aggregates["candidate_shadow_skipped_total"] += row["candidate_shadow_skipped_count"]
            aggregates["rollback_total"] += int(row["rollback_applied"])
            aggregates["exact_match_pass_count"] += int(case_exact_match)

            case_rows.append(row)

        total_cases = len(benchmark_cases)
        summary: dict[str, float | int] = {
            "total_cases": total_cases,
            "exact_match_pass_count": aggregates["exact_match_pass_count"],
            "exact_match_pass_rate": round(aggregates["exact_match_pass_count"] / total_cases, 6) if total_cases else 0.0,
            **aggregates,
        }
        return summary, case_rows
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()


def _count_case_outcomes(case_rows: list[dict[str, Any]]) -> dict[str, int]:
    total = len(case_rows)
    return {
        "correct_as_expected": sum(1 for row in case_rows if row["exact_match"]),
        "unchanged_when_expected_change": sum(1 for row in case_rows if row["unchanged_when_expected_change"]),
        "wrong_change": sum(1 for row in case_rows if row["wrong_change"]),
        "no_change_as_expected": sum(1 for row in case_rows if row["no_change_as_expected"]),
        "candidate_generated_not_applied": sum(
            1 for row in case_rows if row["candidate_generated_count"] > 0 and row["candidate_applied_count"] == 0
        ),
        "unsafe_rejected": sum(1 for row in case_rows if row["candidate_rejected_unsafe_candidate_count"] > 0),
        "rollback_related": sum(1 for row in case_rows if row["rollback_applied"]),
        "protected_no_touch_preservation": 0,
        "total_cases": total,
    }


def _rates(counts: dict[str, int]) -> dict[str, float]:
    total = counts["total_cases"]
    if total == 0:
        return {key: 0.0 for key in counts if key != "total_cases"}
    return {key: round(value / total, 6) for key, value in counts.items() if key != "total_cases"}


def _top_mismatch_slices(case_rows: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, int | str]]:
    slices: Counter[str] = Counter()
    for row in case_rows:
        if row["exact_match"]:
            continue
        tags: list[str] = []
        if row["unchanged_when_expected_change"]:
            tags.append("unchanged_when_expected_change")
        if row["wrong_change"]:
            tags.append("wrong_change")
        if row["candidate_generated_count"] > 0 and row["candidate_applied_count"] == 0:
            tags.append("candidate_generated_not_applied")
        if row["candidate_rejected_no_result_count"] > 0:
            tags.append("candidate_rejected_no_result")
        if row["candidate_ambiguous_count"] > 0 or row["candidate_ambiguous_tie_count"] > 0:
            tags.append("candidate_ambiguous")
        if row["candidate_rejected_morph_blocked_count"] > 0:
            tags.append("morph_blocked")
        if row["candidate_rejected_morph_unknown_count"] > 0:
            tags.append("morph_unknown")
        if row["candidate_rejected_unsafe_candidate_count"] > 0:
            tags.append("unsafe_rejected")
        if row["rollback_applied"]:
            tags.append("rollback_related")
        if not tags:
            tags.append("mismatch_without_candidate_signal")
        slices[" + ".join(tags)] += 1

    return [{"slice": key, "count": value} for key, value in slices.most_common(top_n)]


def _compare_safe_vs_smart(safe_rows: list[dict[str, Any]], smart_rows: list[dict[str, Any]]) -> dict[str, int]:
    improved = 0
    regressed = 0
    output_diff = 0
    for safe_row, smart_row in zip(safe_rows, smart_rows):
        safe_match = bool(safe_row["exact_match"])
        smart_match = bool(smart_row["exact_match"])
        if smart_match and not safe_match:
            improved += 1
        elif safe_match and not smart_match:
            regressed += 1

        if (
            safe_row["unchanged_when_expected_change"] != smart_row["unchanged_when_expected_change"]
            or safe_row["wrong_change"] != smart_row["wrong_change"]
            or safe_row["candidate_applied_count"] != smart_row["candidate_applied_count"]
        ):
            output_diff += 1

    return {
        "smart_improves_expected_match": improved,
        "smart_regresses_expected_match": regressed,
        "cases_with_behavior_delta": output_diff,
    }


def _build_recommended_hints(
    safe_counts: dict[str, int],
    smart_counts: dict[str, int],
    smart_top_slices: list[dict[str, int | str]],
) -> list[str]:
    hints: list[str] = []

    if smart_counts["unchanged_when_expected_change"] > 0:
        hints.append(
            "Проверить top slices с `unchanged_when_expected_change` и приоритизировать минимальные rule-map/словарные точки, "
            "где ожидался безопасный change, но smart baseline оставил текст без изменений."
        )

    if smart_counts["candidate_generated_not_applied"] > 0:
        hints.append(
            "Разобрать случаи `candidate_generated_not_applied`: отделить no-result/ambiguous/morph blockers и выбрать один "
            "минимальный fail-closed шаг (например, точечный словарный coverage gap)."
        )

    if smart_counts["wrong_change"] > 0:
        hints.append(
            "По `wrong_change` проверить, не сосредоточены ли ошибки в одном slice; прежде чем менять runtime, добавить/обновить точечные eval-кейсы "
            "для выбранного slice."
        )

    if smart_counts["unsafe_rejected"] > 0 or smart_counts["rollback_related"] > 0:
        hints.append(
            "Наличие `unsafe_rejected`/`rollback_related` трактовать как safety signal: tuning only через консервативные блокеры/детекторы, "
            "без расширения apply-поведения."
        )

    if not hints and smart_top_slices:
        top_slice = str(smart_top_slices[0]["slice"])
        hints.append(
            f"Текущий недобор компактный; следующий минимальный шаг — проверить top mismatch slice `{top_slice}` и добавить ровно один "
            "узкий deterministic fix после повторного прогона RuSpellGold."
        )

    if not hints:
        hints.append("RuSpellGold report не выявил выраженных недоборов; сохранить baseline без изменений и повторять мониторинг на новых кейсах.")

    return hints


def generate_tuning_report(
    output_md: Path,
    output_json: Path,
    safe_mode: str = DEFAULT_SAFE_MODE,
    smart_mode: str = DEFAULT_SMART_MODE,
) -> dict[str, Any]:
    safe_summary, safe_rows = _evaluate_cases_for_mode(safe_mode)
    smart_summary, smart_rows = _evaluate_cases_for_mode(smart_mode)

    safe_counts = _count_case_outcomes(safe_rows)
    smart_counts = _count_case_outcomes(smart_rows)
    safe_rates = _rates(safe_counts)
    smart_rates = _rates(smart_counts)
    safe_top_slices = _top_mismatch_slices(safe_rows)
    smart_top_slices = _top_mismatch_slices(smart_rows)
    diff_summary = _compare_safe_vs_smart(safe_rows, smart_rows)

    recommended_hints = _build_recommended_hints(safe_counts, smart_counts, smart_top_slices)

    report: dict[str, Any] = {
        "modes": {"safe_default": safe_mode, "smart_baseline": smart_mode},
        "safe_summary": safe_summary,
        "smart_summary": smart_summary,
        "safe_counts": safe_counts,
        "safe_rates": safe_rates,
        "smart_counts": smart_counts,
        "smart_rates": smart_rates,
        "safe_vs_smart_diff": {
            "exact_match_pass_rate_delta": round(
                float(smart_summary["exact_match_pass_rate"]) - float(safe_summary["exact_match_pass_rate"]), 6
            ),
            "exact_match_pass_count_delta": int(smart_summary["exact_match_pass_count"]) - int(safe_summary["exact_match_pass_count"]),
            **diff_summary,
        },
        "top_mismatch_slices": {
            "safe_default": safe_top_slices,
            "smart_baseline": smart_top_slices,
        },
        "recommended_next_minimal_tuning_directions": recommended_hints,
    }

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# RuSpellGold Tuning Report (safe default vs smart baseline)",
        "",
        "## Baseline summary",
        "",
        f"- safe_default_mode: `{safe_mode}`",
        f"- smart_baseline_mode: `{smart_mode}`",
        f"- total_cases: {int(safe_summary['total_cases'])}",
        "",
        "| mode | exact_match_pass_count | exact_match_pass_rate | candidate_generated_total | candidate_applied_total | candidate_generated_not_applied_cases | unchanged_when_expected_change | wrong_change | unsafe_rejected | rollback_related |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| safe_default | {pass_count} | {pass_rate:.6f} | {generated} | {applied} | {not_applied} | {unchanged} | {wrong} | {unsafe} | {rollback} |".format(
            pass_count=int(safe_summary["exact_match_pass_count"]),
            pass_rate=float(safe_summary["exact_match_pass_rate"]),
            generated=int(safe_summary["candidate_generated_total"]),
            applied=int(safe_summary["candidate_applied_total"]),
            not_applied=safe_counts["candidate_generated_not_applied"],
            unchanged=safe_counts["unchanged_when_expected_change"],
            wrong=safe_counts["wrong_change"],
            unsafe=safe_counts["unsafe_rejected"],
            rollback=safe_counts["rollback_related"],
        ),
        "| smart_baseline | {pass_count} | {pass_rate:.6f} | {generated} | {applied} | {not_applied} | {unchanged} | {wrong} | {unsafe} | {rollback} |".format(
            pass_count=int(smart_summary["exact_match_pass_count"]),
            pass_rate=float(smart_summary["exact_match_pass_rate"]),
            generated=int(smart_summary["candidate_generated_total"]),
            applied=int(smart_summary["candidate_applied_total"]),
            not_applied=smart_counts["candidate_generated_not_applied"],
            unchanged=smart_counts["unchanged_when_expected_change"],
            wrong=smart_counts["wrong_change"],
            unsafe=smart_counts["unsafe_rejected"],
            rollback=smart_counts["rollback_related"],
        ),
        "",
        "## Safe vs smart diff",
        "",
        f"- exact_match_pass_rate_delta: {report['safe_vs_smart_diff']['exact_match_pass_rate_delta']:.6f}",
        f"- exact_match_pass_count_delta: {report['safe_vs_smart_diff']['exact_match_pass_count_delta']}",
        f"- smart_improves_expected_match: {report['safe_vs_smart_diff']['smart_improves_expected_match']}",
        f"- smart_regresses_expected_match: {report['safe_vs_smart_diff']['smart_regresses_expected_match']}",
        f"- cases_with_behavior_delta: {report['safe_vs_smart_diff']['cases_with_behavior_delta']}",
        "",
        "## Outcome buckets (counts and rates)",
        "",
        "| bucket | safe_count | safe_rate | smart_count | smart_rate |",
        "|---|---:|---:|---:|---:|",
    ]

    for bucket in (
        "correct_as_expected",
        "unchanged_when_expected_change",
        "wrong_change",
        "no_change_as_expected",
        "protected_no_touch_preservation",
        "candidate_generated_not_applied",
        "unsafe_rejected",
        "rollback_related",
    ):
        lines.append(
            "| {bucket} | {safe_count} | {safe_rate:.6f} | {smart_count} | {smart_rate:.6f} |".format(
                bucket=bucket,
                safe_count=safe_counts[bucket],
                safe_rate=safe_rates[bucket],
                smart_count=smart_counts[bucket],
                smart_rate=smart_rates[bucket],
            )
        )

    lines.extend(["", "## Top high-signal mismatch slices", ""])
    lines.append("### safe_default")
    for row in safe_top_slices:
        lines.append(f"- {row['slice']}: {row['count']}")
    if not safe_top_slices:
        lines.append("- no mismatches")

    lines.append("")
    lines.append("### smart_baseline")
    for row in smart_top_slices:
        lines.append(f"- {row['slice']}: {row['count']}")
    if not smart_top_slices:
        lines.append("- no mismatches")

    lines.extend(["", "## recommended next minimal tuning directions", ""])
    for hint in recommended_hints:
        lines.append(f"- {hint}")

    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate RuSpellGold tuning report for safe vs smart baseline. "
            f"Canonical command: {CANONICAL_COMMAND}"
        )
    )
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Path to markdown report")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="Path to machine-readable JSON summary")
    parser.add_argument("--safe-mode", default=DEFAULT_SAFE_MODE, help="RuSpellGold harness mode for safe baseline")
    parser.add_argument("--smart-mode", default=DEFAULT_SMART_MODE, help="RuSpellGold harness mode for smart baseline")
    args = parser.parse_args()

    hint = _wrong_invocation_hint()
    if hint:
        print(hint, file=sys.stderr)

    try:
        report = generate_tuning_report(
            output_md=Path(args.output_md),
            output_json=Path(args.output_json),
            safe_mode=args.safe_mode,
            smart_mode=args.smart_mode,
        )
    except RuntimeError as exc:
        raise SystemExit(_diagnose_runtime_error(exc)) from exc

    print(
        "ruspellgold tuning report summary: "
        f"safe_mode={args.safe_mode}, "
        f"smart_mode={args.smart_mode}, "
        f"total_cases={report['safe_summary']['total_cases']}, "
        f"exact_match_pass_rate_delta={report['safe_vs_smart_diff']['exact_match_pass_rate_delta']:.6f}, "
        f"output_md={args.output_md}, "
        f"output_json={args.output_json}"
    )


if __name__ == "__main__":
    main()
