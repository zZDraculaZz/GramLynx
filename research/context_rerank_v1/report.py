from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _mode_summary(rows: list[dict[str, Any]], output_key: str) -> dict[str, Any]:
    total = len(rows)
    exact = 0
    wrong_change = 0
    smart_regresses_expected_match = 0
    rollback_related = 0

    for row in rows:
        output = str(row[output_key])
        expected = str(row["expected_clean_text"])
        original = str(row["input_text"])
        current_apply_output = str(row["current_apply_output"])

        if output == expected:
            exact += 1
        if output != expected and output != original:
            wrong_change += 1
        if output != expected and current_apply_output == expected:
            smart_regresses_expected_match += 1

        if output_key == "current_apply_output" and bool(row.get("current_apply_rollback_related", False)):
            rollback_related += 1
        if output_key == "research_replay_v1_output" and bool(row.get("research_replay_v1_rollback_related", False)):
            rollback_related += 1
        if output_key == "research_replay_v2_output" and bool(row.get("research_replay_v2_rollback_related", False)):
            rollback_related += 1

    return {
        "total_cases": total,
        "exact_match_pass_count": exact,
        "exact_match_pass_rate": (exact / total) if total else 0.0,
        "wrong_change": wrong_change,
        "smart_regresses_expected_match": smart_regresses_expected_match,
        "rollback_related": rollback_related,
    }


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    report = {
        "baseline": _mode_summary(rows, "baseline_output"),
        "current_apply": _mode_summary(rows, "current_apply_output"),
        "research_replay_v1": _mode_summary(rows, "research_replay_v1_output"),
        "research_replay_v2": _mode_summary(rows, "research_replay_v2_output"),
        "buckets": {
            "research_v1_beats_current_apply": [
                r
                for r in rows
                if r["research_replay_v1_output"] == r["expected_clean_text"]
                and r["current_apply_output"] != r["expected_clean_text"]
            ],
            "research_v1_worse_than_current_apply": [
                r
                for r in rows
                if r["research_replay_v1_output"] != r["expected_clean_text"]
                and r["current_apply_output"] == r["expected_clean_text"]
            ],
            "research_v2_beats_current_apply": [
                r
                for r in rows
                if r["research_replay_v2_output"] == r["expected_clean_text"]
                and r["current_apply_output"] != r["expected_clean_text"]
            ],
            "research_v2_worse_than_current_apply": [
                r
                for r in rows
                if r["research_replay_v2_output"] != r["expected_clean_text"]
                and r["current_apply_output"] == r["expected_clean_text"]
            ],
        },
    }
    report["bucket_counts"] = {
        "research_v1_beats_current_apply": len(report["buckets"]["research_v1_beats_current_apply"]),
        "research_v1_worse_than_current_apply": len(report["buckets"]["research_v1_worse_than_current_apply"]),
        "research_v2_beats_current_apply": len(report["buckets"]["research_v2_beats_current_apply"]),
        "research_v2_worse_than_current_apply": len(report["buckets"]["research_v2_worse_than_current_apply"]),
        "beam_changed_decision_count": sum(1 for r in rows if bool(r.get("beam_changed_decision", False))),
    }
    report["v2_score_contribution"] = {
        "base_component_sum": sum(float(r.get("v2_base_component", 0.0)) for r in rows),
        "kenlm_component_sum": sum(float(r.get("v2_kenlm_component", 0.0)) for r in rows),
    }
    return report


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Offline Context Rerank v1 Report", ""]
    for mode in ("baseline", "current_apply", "research_replay_v1", "research_replay_v2"):
        data = summary[mode]
        lines.append(f"## {mode}")
        lines.append(f"- total_cases: {data['total_cases']}")
        lines.append(f"- exact_match_pass_count: {data['exact_match_pass_count']}")
        lines.append(f"- exact_match_pass_rate: {data['exact_match_pass_rate']:.4f}")
        lines.append(f"- wrong_change: {data['wrong_change']}")
        lines.append(f"- smart_regresses_expected_match: {data['smart_regresses_expected_match']}")
        lines.append(f"- rollback_related: {data['rollback_related']}")
        lines.append("")

    counts = summary.get("bucket_counts", {})
    lines.append("## buckets")
    for key in (
        "research_v1_beats_current_apply",
        "research_v1_worse_than_current_apply",
        "research_v2_beats_current_apply",
        "research_v2_worse_than_current_apply",
        "beam_changed_decision_count",
    ):
        lines.append(f"- {key}: {counts.get(key, 0)}")

    contrib = summary.get("v2_score_contribution", {})
    lines.append("\n## v2 score contribution")
    lines.append(f"- base_component_sum: {contrib.get('base_component_sum', 0.0):.4f}")
    lines.append(f"- kenlm_component_sum: {contrib.get('kenlm_component_sum', 0.0):.4f}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render offline context rerank report")
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    args.output_md.write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
