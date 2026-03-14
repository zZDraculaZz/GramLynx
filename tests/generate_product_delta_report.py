"""Generate delta report: safe default profile vs smart baseline profile on product pack."""
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

DEFAULT_CASES_PATH = Path("tests/cases/product_regression_user_texts.yml")
DEFAULT_SAFE_CONFIG = Path("config.example.yml")
DEFAULT_SMART_CONFIG = Path("config.smart_baseline_staging.yml")
DEFAULT_OUTPUT_JSONL = Path("product_delta_report.jsonl")
DEFAULT_OUTPUT_MD = Path("product_delta_report.md")


@dataclass(frozen=True)
class ProductCase:
    input_text: str
    expected_clean_text: str
    category: str | None
    source: str


def _load_cases(path: Path) -> tuple[ProductCase, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid product regression pack format")

    rows = payload.get("smart")
    if not isinstance(rows, list) or not rows:
        raise ValueError("product regression pack is empty")

    cases: list[ProductCase] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"invalid product case row at index {index}")
        input_text = row.get("input")
        expected = row.get("expected_clean_text")
        category = row.get("category")
        if not isinstance(input_text, str) or not isinstance(expected, str):
            raise ValueError(f"invalid product case schema at index {index}")
        if category is not None and not isinstance(category, str):
            raise ValueError(f"invalid product category at index {index}")

        cases.append(
            ProductCase(
                input_text=input_text,
                expected_clean_text=expected,
                category=category,
                source="product_regression_pack",
            )
        )

    return tuple(cases)


def _clean_with_config(config_path: Path, input_text: str, correlation_id: str) -> str:
    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(config_path)
    reset_app_config_cache()
    try:
        orchestrator = Orchestrator(correlation_id=correlation_id)
        with contextlib.redirect_stdout(io.StringIO()):
            return orchestrator.clean(input_text, mode="smart")
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()


def _delta_reason(changed_between_profiles: bool, safe_matches_expected: bool, smart_matches_expected: bool) -> str | None:
    if not changed_between_profiles:
        return None
    if smart_matches_expected and not safe_matches_expected:
        return "smart_improves_expected_match"
    if safe_matches_expected and not smart_matches_expected:
        return "smart_regresses_expected_match"
    if smart_matches_expected and safe_matches_expected:
        return "both_match_expected_but_different_output"
    return "profile_outputs_differ_need_human_review"


def generate_delta_report(
    cases_path: Path,
    safe_config_path: Path,
    smart_config_path: Path,
    output_jsonl: Path,
    output_md: Path,
) -> dict[str, int]:
    cases = _load_cases(cases_path)

    rows: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        safe_output = _clean_with_config(safe_config_path, case.input_text, f"delta-safe-{index}")
        smart_output = _clean_with_config(smart_config_path, case.input_text, f"delta-smart-{index}")

        changed_between_profiles = safe_output != smart_output
        safe_matches_expected = safe_output == case.expected_clean_text
        smart_matches_expected = smart_output == case.expected_clean_text
        reason = _delta_reason(changed_between_profiles, safe_matches_expected, smart_matches_expected)

        rows.append(
            {
                "input_text": case.input_text,
                "expected_clean_text": case.expected_clean_text,
                "output_safe_default": safe_output,
                "output_smart_baseline": smart_output,
                "changed_between_profiles": changed_between_profiles,
                "smart_matches_expected": smart_matches_expected,
                "safe_matches_expected": safe_matches_expected,
                "user_visible_delta_reason": reason,
                "category": case.category,
                "source": case.source,
            }
        )

    total_cases = len(rows)
    unchanged_across_profiles = sum(1 for row in rows if row["changed_between_profiles"] is False)
    changed_only_in_smart_baseline = sum(1 for row in rows if row["changed_between_profiles"] is True)
    smart_expected_matches = sum(1 for row in rows if row["smart_matches_expected"] is True)
    safe_expected_matches = sum(1 for row in rows if row["safe_matches_expected"] is True)
    cases_needing_human_look = sum(
        1
        for row in rows
        if row["changed_between_profiles"] is True
        and row["smart_matches_expected"] == row["safe_matches_expected"]
    )

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    with output_jsonl.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    lines = [
        "# Product Delta Report (safe default vs smart baseline)",
        "",
        f"- cases_source: `{cases_path}`",
        f"- safe_config: `{safe_config_path}`",
        f"- smart_config: `{smart_config_path}`",
        "",
        "## Aggregates",
        "",
        f"- total_cases: {total_cases}",
        f"- unchanged_across_profiles: {unchanged_across_profiles}",
        f"- changed_only_in_smart_baseline: {changed_only_in_smart_baseline}",
        f"- smart_expected_matches: {smart_expected_matches}",
        f"- safe_expected_matches: {safe_expected_matches}",
        f"- cases_needing_human_look: {cases_needing_human_look}",
        "",
        "## Cases with profile delta",
        "",
    ]

    delta_rows = [row for row in rows if row["changed_between_profiles"] is True]
    for index, row in enumerate(delta_rows, start=1):
        lines.extend(
            [
                f"### Delta Case {index}",
                f"- category: `{row['category']}`" if row.get("category") else "- category: _not provided_",
                f"- source: `{row['source']}`",
                f"- user_visible_delta_reason: `{row['user_visible_delta_reason']}`" if row.get("user_visible_delta_reason") else "- user_visible_delta_reason: _not provided_",
                "- input_text:",
                f"  - {row['input_text']}",
                "- output_safe_default:",
                f"  - {row['output_safe_default']}",
                "- output_smart_baseline:",
                f"  - {row['output_smart_baseline']}",
                f"- expected_clean_text: `{row['expected_clean_text']}`",
                "",
            ]
        )

    output_md.write_text("\n".join(lines), encoding="utf-8")
    return {
        "total_cases": total_cases,
        "unchanged_across_profiles": unchanged_across_profiles,
        "changed_only_in_smart_baseline": changed_only_in_smart_baseline,
        "smart_expected_matches": smart_expected_matches,
        "safe_expected_matches": safe_expected_matches,
        "cases_needing_human_look": cases_needing_human_look,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product delta report between safe default and smart baseline")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to product regression pack YAML")
    parser.add_argument("--safe-config", default=str(DEFAULT_SAFE_CONFIG), help="Path to safe-default YAML config")
    parser.add_argument("--smart-config", default=str(DEFAULT_SMART_CONFIG), help="Path to smart-baseline YAML config")
    parser.add_argument("--output-jsonl", default=str(DEFAULT_OUTPUT_JSONL), help="Path to output JSONL report")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Path to output markdown report")
    args = parser.parse_args()

    summary = generate_delta_report(
        cases_path=Path(args.cases),
        safe_config_path=Path(args.safe_config),
        smart_config_path=Path(args.smart_config),
        output_jsonl=Path(args.output_jsonl),
        output_md=Path(args.output_md),
    )

    print(
        "product delta report summary: "
        f"total_cases={summary['total_cases']}, "
        f"unchanged_across_profiles={summary['unchanged_across_profiles']}, "
        f"changed_only_in_smart_baseline={summary['changed_only_in_smart_baseline']}, "
        f"smart_expected_matches={summary['smart_expected_matches']}, "
        f"safe_expected_matches={summary['safe_expected_matches']}, "
        f"cases_needing_human_look={summary['cases_needing_human_look']}, "
        f"output_jsonl={args.output_jsonl}, "
        f"output_md={args.output_md}"
    )


if __name__ == "__main__":
    main()
