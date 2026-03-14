"""Offline pilot/manual review utility for smart baseline.

Reads a local JSONL corpus, runs smart-mode cleaning, and writes a markdown review report.
Prints only compact aggregated summary to stdout.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent / "cases" / "pilot_manual_review.jsonl"
DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[1] / "pilot_review_report.md"
DEFAULT_BASELINE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.smart_baseline_staging.yml"

_ALLOWED_KEYS = {"input_text", "expected_clean_text", "tag", "note"}


@dataclass(frozen=True)
class PilotCase:
    input_text: str
    expected_clean_text: str | None
    tag: str | None
    note: str | None


def _load_cases(path: Path) -> tuple[PilotCase, ...]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"pilot corpus not found: {path}")

    cases: list[PilotCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = line.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid pilot row at line {line_no}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"invalid pilot row type at line {line_no}")

        unknown = set(payload) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(f"invalid pilot schema at line {line_no}")

        input_text = payload.get("input_text")
        expected_clean_text = payload.get("expected_clean_text")
        tag = payload.get("tag")
        note = payload.get("note")

        if not isinstance(input_text, str) or not input_text:
            raise ValueError(f"invalid input_text at line {line_no}")

        if expected_clean_text is not None and not isinstance(expected_clean_text, str):
            raise ValueError(f"invalid expected_clean_text at line {line_no}")
        if tag is not None and not isinstance(tag, str):
            raise ValueError(f"invalid tag at line {line_no}")
        if note is not None and not isinstance(note, str):
            raise ValueError(f"invalid note at line {line_no}")

        cases.append(
            PilotCase(
                input_text=input_text,
                expected_clean_text=expected_clean_text,
                tag=tag,
                note=note,
            )
        )

    if not cases:
        raise ValueError("pilot corpus is empty")

    return tuple(cases)


def _status(input_text: str, clean_text: str, expected_clean_text: str | None) -> str:
    if expected_clean_text is not None:
        return "exact_match" if clean_text == expected_clean_text else "changed" if clean_text != input_text else "unchanged"
    return "changed" if clean_text != input_text else "unchanged"


def run_review(corpus_path: Path, report_path: Path, baseline_config_path: Path) -> dict[str, float | int]:
    cases = _load_cases(corpus_path)

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(baseline_config_path)
    reset_app_config_cache()

    try:
        changed_count = 0
        unchanged_count = 0
        expected_cases = 0
        exact_match_count = 0
        rollback_total = 0
        unsafe_total = 0
        candidate_generated_total = 0
        candidate_applied_total = 0

        report_lines = [
            "# Pilot Manual Review Report",
            "",
            f"- corpus: `{corpus_path}`",
            "- mode: `smart`",
            "",
            "## Cases",
            "",
        ]

        for index, case in enumerate(cases, start=1):
            orchestrator = Orchestrator(correlation_id=f"pilot-review-{index}")
            with contextlib.redirect_stdout(io.StringIO()):
                clean_text = orchestrator.clean(case.input_text, mode="smart")
            stats = orchestrator.last_run_stats

            status = _status(case.input_text, clean_text, case.expected_clean_text)
            if clean_text == case.input_text:
                unchanged_count += 1
            else:
                changed_count += 1

            if case.expected_clean_text is not None:
                expected_cases += 1
                exact_match_count += int(clean_text == case.expected_clean_text)

            rollback_total += int(bool(stats.get("rollback_applied", False)))
            unsafe_total += int(stats.get("candidate_rejected_unsafe_candidate_count", 0))
            candidate_generated_total += int(stats.get("candidate_generated_count", 0))
            candidate_applied_total += int(stats.get("candidate_applied_count", 0))

            report_lines.extend(
                [
                    f"### Case {index}",
                    f"- status: `{status}`",
                    "- input_text:",
                    f"  - {case.input_text}",
                    "- clean_text:",
                    f"  - {clean_text}",
                    "- mode: `smart`",
                    f"- expected_clean_text: `{case.expected_clean_text}`" if case.expected_clean_text is not None else "- expected_clean_text: _not provided_",
                    f"- tag: `{case.tag}`" if case.tag else "- tag: _not provided_",
                    f"- note: `{case.note}`" if case.note else "- note: _not provided_",
                    "",
                ]
            )

        total_cases = len(cases)
        exact_match_rate = (exact_match_count / expected_cases) if expected_cases else 0.0

        report_lines.extend(
            [
                "## Summary",
                "",
                f"- total_cases: {total_cases}",
                f"- changed_count: {changed_count}",
                f"- unchanged_count: {unchanged_count}",
                f"- exact_match_count: {exact_match_count}",
                f"- exact_match_rate: {exact_match_rate:.6f}",
                f"- rollback_total: {rollback_total}",
                f"- unsafe_total: {unsafe_total}",
                f"- candidate_generated_total: {candidate_generated_total}",
                f"- candidate_applied_total: {candidate_applied_total}",
                "",
            ]
        )

        report_path.write_text("\n".join(report_lines), encoding="utf-8")

        return {
            "total_cases": total_cases,
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "exact_match_count": exact_match_count,
            "exact_match_rate": round(exact_match_rate, 6),
            "rollback_total": rollback_total,
            "unsafe_total": unsafe_total,
            "candidate_generated_total": candidate_generated_total,
            "candidate_applied_total": candidate_applied_total,
        }
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local pilot/manual review for smart baseline")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_PATH), help="Path to pilot JSONL corpus")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Path to markdown output report")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_BASELINE_CONFIG_PATH),
        help="Path to baseline config YAML",
    )
    args = parser.parse_args()

    summary = run_review(Path(args.corpus), Path(args.report), Path(args.config))
    print(
        "pilot review summary: "
        f"total_cases={int(summary['total_cases'])}, "
        f"changed_count={int(summary['changed_count'])}, "
        f"unchanged_count={int(summary['unchanged_count'])}, "
        f"exact_match_count={int(summary['exact_match_count'])}, "
        f"exact_match_rate={float(summary['exact_match_rate']):.6f}, "
        f"rollback_total={int(summary['rollback_total'])}, "
        f"unsafe_total={int(summary['unsafe_total'])}, "
        f"candidate_generated_total={int(summary['candidate_generated_total'])}, "
        f"candidate_applied_total={int(summary['candidate_applied_total'])}, "
        f"report={args.report}"
    )


if __name__ == "__main__":
    main()
