"""Generate compact human-readable usefulness showcase from product delta report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _is_clear_improvement(row: dict[str, object]) -> bool:
    reason = row.get("user_visible_delta_reason")
    return bool(
        row.get("changed_between_profiles") is True
        and row.get("smart_matches_expected") is True
        and row.get("safe_matches_expected") is False
        and reason == "smart_improves_expected_match"
    )


def _is_safe_preservation(row: dict[str, object]) -> bool:
    if row.get("changed_between_profiles") is not False:
        return False

    input_text = str(row.get("input_text", ""))
    safe_out = str(row.get("output_safe_default", ""))
    smart_out = str(row.get("output_smart_baseline", ""))
    expected = str(row.get("expected_clean_text", ""))
    return input_text == safe_out == smart_out == expected


def _is_caution(row: dict[str, object]) -> bool:
    reason = str(row.get("user_visible_delta_reason") or "")
    if reason in {
        "smart_regresses_expected_match",
        "both_match_expected_but_different_output",
        "profile_outputs_differ_need_human_review",
    }:
        return True

    return bool(
        row.get("changed_between_profiles") is True
        and row.get("smart_matches_expected") is not True
        and row.get("safe_matches_expected") is not True
    )


def _format_case(row: dict[str, object]) -> list[str]:
    category = row.get("category")
    reason = row.get("user_visible_delta_reason")
    lines = [
        f"- category: `{category}`" if category else "- category: _not provided_",
        f"- short_reason: `{reason}`" if reason else "- short_reason: _not provided_",
        "- input_text:",
        f"  - {row.get('input_text', '')}",
        "- output_safe_default:",
        f"  - {row.get('output_safe_default', '')}",
        "- output_smart_baseline:",
        f"  - {row.get('output_smart_baseline', '')}",
        f"- expected_clean_text: `{row.get('expected_clean_text', '')}`",
    ]
    return lines


def generate_usefulness_showcase(delta_jsonl: Path, output_md: Path, per_section_limit: int = 5) -> dict[str, int]:
    rows = _read_rows(delta_jsonl)

    improvements = [row for row in rows if _is_clear_improvement(row)][:per_section_limit]
    preservations = [row for row in rows if _is_safe_preservation(row)][:per_section_limit]
    caution_rows = [row for row in rows if _is_caution(row)][:per_section_limit]

    output_md.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Smart Baseline Usefulness Showcase (user-like texts)",
        "",
        f"- source_delta_report: `{delta_jsonl}`",
        f"- total_rows: {len(rows)}",
        f"- showcased_per_section_limit: {per_section_limit}",
        "",
        "## Что сервис улучшает",
        "",
    ]

    if improvements:
        for index, row in enumerate(improvements, start=1):
            lines.extend([f"### Improvement case {index}", *_format_case(row), ""])
    else:
        lines.extend(["- нет кейсов в выбранной выборке", ""])

    lines.extend(["## Что сервис специально не трогает", ""])
    if preservations:
        for index, row in enumerate(preservations, start=1):
            lines.extend([f"### Preservation case {index}", *_format_case(row), ""])
    else:
        lines.extend(["- нет кейсов в выбранной выборке", ""])

    lines.extend(["## Какие кейсы требуют осторожности/ручного review", ""])
    if caution_rows:
        for index, row in enumerate(caution_rows, start=1):
            lines.extend([f"### Caution case {index}", *_format_case(row), ""])
    else:
        lines.extend(["- нет кейсов в выбранной выборке", ""])

    output_md.write_text("\n".join(lines), encoding="utf-8")

    return {
        "total_rows": len(rows),
        "improvement_cases": len(improvements),
        "preservation_cases": len(preservations),
        "caution_cases": len(caution_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate compact smart-baseline usefulness showcase")
    parser.add_argument("--delta-jsonl", default="product_delta_report.jsonl")
    parser.add_argument("--output-md", default="smart_baseline_usefulness_showcase.md")
    parser.add_argument("--per-section-limit", type=int, default=5)
    args = parser.parse_args()

    summary = generate_usefulness_showcase(
        delta_jsonl=Path(args.delta_jsonl),
        output_md=Path(args.output_md),
        per_section_limit=max(1, args.per_section_limit),
    )
    print(
        "usefulness showcase summary: "
        f"total_rows={summary['total_rows']}, "
        f"improvement_cases={summary['improvement_cases']}, "
        f"preservation_cases={summary['preservation_cases']}, "
        f"caution_cases={summary['caution_cases']}"
    )


if __name__ == "__main__":
    main()
