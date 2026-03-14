"""Offline summary report for current candidate-generation baseline.

Runs internal and external evaluation harnesses and prints only aggregated metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import eval_candidate_harness, eval_ruspellgold_harness

MODES: tuple[str, ...] = ("baseline", "symspell_shadow", "symspell_apply")


def _render_section(title: str, stats_by_mode: dict[str, dict[str, float | int]]) -> str:
    lines = [f"## {title}", ""]
    lines.append(
        "| mode | exact_match_pass_rate | candidate_generated_total | candidate_applied_total | candidate_rejected_no_result_total | candidate_ambiguous_total | rollback_total |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")

    for mode in MODES:
        stats = stats_by_mode[mode]
        lines.append(
            "| {mode} | {pass_rate:.6f} | {generated} | {applied} | {no_result} | {ambiguous} | {rollback} |".format(
                mode=mode,
                pass_rate=float(stats["exact_match_pass_rate"]),
                generated=int(stats["candidate_generated_total"]),
                applied=int(stats["candidate_applied_total"]),
                no_result=int(stats["candidate_rejected_no_result_total"]),
                ambiguous=int(stats["candidate_ambiguous_total"]),
                rollback=int(stats["rollback_total"]),
            )
        )

    lines.append("")
    return "\n".join(lines)


def _quality_lift_present(internal: dict[str, dict[str, float | int]], external: dict[str, dict[str, float | int]]) -> bool:
    return (
        float(internal["symspell_apply"]["exact_match_pass_rate"]) > float(internal["baseline"]["exact_match_pass_rate"])
        and float(external["symspell_apply"]["exact_match_pass_rate"]) > float(external["baseline"]["exact_match_pass_rate"])
    )


def _safety_stable(internal: dict[str, dict[str, float | int]], external: dict[str, dict[str, float | int]]) -> bool:
    def _ok(stats: dict[str, float | int]) -> bool:
        return int(stats["rollback_total"]) == 0 and int(stats["candidate_rejected_unsafe_candidate_total"]) == 0

    return all(_ok(internal[m]) for m in MODES) and all(_ok(external[m]) for m in MODES)


def build_report() -> str:
    internal_all = eval_candidate_harness.evaluate_all_modes()
    external_all = eval_ruspellgold_harness.evaluate_all_modes()

    internal = {mode: internal_all[mode] for mode in MODES}
    external = {mode: external_all[mode] for mode in MODES}

    quality_lift = _quality_lift_present(internal, external)
    safety_stable = _safety_stable(internal, external)

    lines = [
        "# Candidate Baseline Summary",
        "",
        _render_section("Internal Harness", internal),
        _render_section("External Benchmark Harness", external),
        "## Verdict",
        "",
        f"- quality lift present: {'yes' if quality_lift else 'no'}",
        f"- safety stable: {'yes' if safety_stable else 'no'}",
    ]
    return "\n".join(lines)


def main() -> None:
    print(build_report())


if __name__ == "__main__":
    main()
