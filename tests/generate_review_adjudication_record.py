"""Generate template-first human review adjudication record for rollout evidence bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid json object: {path}")
    return payload


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("invalid jsonl row type")
        count += 1
    return count


def _decide_outcome(
    missing_inputs: bool,
    blocking_case_count: int,
    caution_case_count: int,
    unresolved_case_count: int,
    reviewed_case_count: int,
) -> tuple[str, str]:
    if missing_inputs or blocking_case_count > 0:
        return "blocked", "inspect_blocking_cases"
    if reviewed_case_count == 0:
        return "needs_follow_up", "keep_shadow_only"
    if unresolved_case_count > 0 or caution_case_count > 0:
        return "needs_follow_up", "rerun_manual_review_after_changes"
    return "approved_for_controlled_apply_review", "proceed_to_controlled_apply_review"


def build_review_adjudication_record(
    bundle_dir: Path,
    output_json: Path,
    output_md: Path,
    blocking_case_count: int,
    caution_case_count: int,
    accepted_case_count: int,
    reviewer_notes: str,
) -> dict[str, object]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"bundle manifest not found: {manifest_path}")

    manifest = _read_json(manifest_path)
    profile_name = str(manifest.get("profile_name", "unknown"))
    config_path = str(manifest.get("config_path", "unknown"))

    manual_review_jsonl = bundle_dir / "manual_review_pack.jsonl"
    total_review_candidates = _count_jsonl_rows(manual_review_jsonl)
    missing_inputs = total_review_candidates == 0

    reviewed_case_count = blocking_case_count + caution_case_count + accepted_case_count
    unresolved_case_count = max(total_review_candidates - reviewed_case_count, 0)

    review_outcome, recommended_follow_up = _decide_outcome(
        missing_inputs=missing_inputs,
        blocking_case_count=blocking_case_count,
        caution_case_count=caution_case_count,
        unresolved_case_count=unresolved_case_count,
        reviewed_case_count=reviewed_case_count,
    )

    record: dict[str, object] = {
        "profile_name": profile_name,
        "config_path": config_path,
        "source_bundle_path": str(bundle_dir),
        "review_candidate_count": total_review_candidates,
        "reviewed_case_count": reviewed_case_count,
        "blocking_case_count": blocking_case_count,
        "caution_case_count": caution_case_count,
        "accepted_case_count": accepted_case_count,
        "unresolved_case_count": unresolved_case_count,
        "reviewer_notes": reviewer_notes,
        "review_outcome": review_outcome,
        "recommended_follow_up": recommended_follow_up,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Smart Baseline Review Adjudication Record",
        "",
        f"- profile_name: `{profile_name}`",
        f"- config_path: `{config_path}`",
        f"- source_bundle_path: `{bundle_dir}`",
        f"- review_candidate_count: {total_review_candidates}",
        f"- reviewed_case_count: {reviewed_case_count}",
        f"- blocking_case_count: {blocking_case_count}",
        f"- caution_case_count: {caution_case_count}",
        f"- accepted_case_count: {accepted_case_count}",
        f"- unresolved_case_count: {unresolved_case_count}",
        f"- review_outcome: `{review_outcome}`",
        f"- recommended_follow_up: `{recommended_follow_up}`",
        "",
        "## Reviewer notes",
        "",
        reviewer_notes if reviewer_notes else "_not provided_",
        "",
        "## Interpretation",
        "",
        "- `blocked`: есть блокирующие findings или отсутствуют минимальные входы для review.",
        "- `needs_follow_up`: review не завершён или есть caution-кейсы.",
        "- `approved_for_controlled_apply_review`: review закрыт без blocking/caution/unresolved кейсов.",
    ]
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate review adjudication record from rollout evidence bundle")
    parser.add_argument("--bundle-dir", default="rollout_evidence_bundle/smart_baseline_staging")
    parser.add_argument("--output-json", default="review_adjudication.json")
    parser.add_argument("--output-md", default="review_adjudication.md")
    parser.add_argument("--blocking-case-count", type=int, default=0)
    parser.add_argument("--caution-case-count", type=int, default=0)
    parser.add_argument("--accepted-case-count", type=int, default=0)
    parser.add_argument("--reviewer-notes", default="")
    args = parser.parse_args()

    record = build_review_adjudication_record(
        bundle_dir=Path(args.bundle_dir),
        output_json=Path(args.output_json),
        output_md=Path(args.output_md),
        blocking_case_count=max(args.blocking_case_count, 0),
        caution_case_count=max(args.caution_case_count, 0),
        accepted_case_count=max(args.accepted_case_count, 0),
        reviewer_notes=args.reviewer_notes,
    )

    print(
        "review adjudication summary: "
        f"review_outcome={record['review_outcome']}, "
        f"recommended_follow_up={record['recommended_follow_up']}, "
        f"reviewed_case_count={record['reviewed_case_count']}, "
        f"unresolved_case_count={record['unresolved_case_count']}"
    )


if __name__ == "__main__":
    main()
