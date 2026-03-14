"""Generate decision-ready verdict from an existing rollout evidence bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid json object: {path}")
    return payload


def _load_bundle_inputs(bundle_dir: Path) -> tuple[dict[str, object], dict[str, object] | None]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"bundle manifest not found: {manifest_path}")
    manifest = _read_json(manifest_path)

    readiness_path = bundle_dir / "readiness_summary.json"
    readiness = _read_json(readiness_path) if readiness_path.exists() else None
    return manifest, readiness


def _choose_verdict(
    final_readiness_status: str,
    bundle_complete: bool,
    warnings: list[str],
    review_needed_reasons: list[str],
    config_integrity_status: str,
    product_regression_status: str,
) -> tuple[str, str]:
    has_blocking_warning = any(
        item.startswith("config_missing") or item.startswith("config_invalid_yaml") or item == "bundle_incomplete"
        for item in warnings
    )

    if final_readiness_status == "not_ready" or config_integrity_status == "fail" or product_regression_status == "failed":
        return "hold_not_ready", "fix_config_drift"

    if has_blocking_warning or not bundle_complete:
        return "hold_not_ready", "regenerate_missing_artifacts"

    if final_readiness_status == "ready_for_review" and not review_needed_reasons:
        return "eligible_for_controlled_apply", "proceed_to_controlled_apply_review"

    if final_readiness_status == "ready_for_review":
        return "review_before_apply", "inspect_manual_review_pack"

    if "product_regression_not_run" in review_needed_reasons:
        return "review_before_apply", "rerun_product_regression"

    if review_needed_reasons:
        return "review_before_apply", "inspect_manual_review_pack"

    return "review_before_apply", "regenerate_missing_artifacts"


def build_decision_record(bundle_dir: Path, output_json: Path, output_md: Path) -> dict[str, object]:
    manifest, readiness = _load_bundle_inputs(bundle_dir)

    profile_name = str(manifest.get("profile_name", "unknown"))
    config_path = str(manifest.get("config_path", "unknown"))
    bundle_complete = bool(manifest.get("bundle_complete", False))

    warnings = [str(item) for item in manifest.get("warnings", []) if isinstance(item, str)]
    missing_artifacts = [str(item) for item in manifest.get("missing_artifacts", []) if isinstance(item, str)]

    final_readiness_status = str(manifest.get("final_readiness_status", "not_ready"))
    config_integrity_status = "unknown"
    product_regression_status = "unknown"
    delta_report_status = "unknown"
    manual_review_pack_status = "unknown"
    review_needed_reasons: list[str] = []

    if readiness is not None:
        final_readiness_status = str(readiness.get("final_status", final_readiness_status))
        config_integrity_status = str(readiness.get("config_integrity_status", "unknown"))
        product_regression_status = str(readiness.get("product_regression_status", "unknown"))
        delta_report_status = str(readiness.get("delta_report_status", "unknown"))
        manual_review_pack_status = str(readiness.get("manual_review_pack_status", "unknown"))
        review_needed_reasons = [
            str(item) for item in readiness.get("review_needed_reasons", []) if isinstance(item, str)
        ]
        warnings.extend(str(item) for item in readiness.get("warnings", []) if isinstance(item, str))

    warnings = sorted(set(warnings))
    review_needed_reasons = sorted(set(review_needed_reasons))

    verdict, next_action = _choose_verdict(
        final_readiness_status=final_readiness_status,
        bundle_complete=bundle_complete,
        warnings=warnings,
        review_needed_reasons=review_needed_reasons,
        config_integrity_status=config_integrity_status,
        product_regression_status=product_regression_status,
    )

    record: dict[str, object] = {
        "bundle_dir": str(bundle_dir),
        "profile_name": profile_name,
        "config_path": config_path,
        "final_readiness_status": final_readiness_status,
        "config_integrity_status": config_integrity_status,
        "product_regression_status": product_regression_status,
        "delta_report_status": delta_report_status,
        "manual_review_pack_status": manual_review_pack_status,
        "bundle_complete": bundle_complete,
        "missing_artifacts": missing_artifacts,
        "warnings": warnings,
        "review_needed_reasons": review_needed_reasons,
        "verdict": verdict,
        "recommended_next_action": next_action,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Smart Baseline Rollout Decision Record",
        "",
        f"- bundle_dir: `{bundle_dir}`",
        f"- profile_name: `{profile_name}`",
        f"- config_path: `{config_path}`",
        f"- final_readiness_status: `{final_readiness_status}`",
        f"- config_integrity_status: `{config_integrity_status}`",
        f"- product_regression_status: `{product_regression_status}`",
        f"- delta_report_status: `{delta_report_status}`",
        f"- manual_review_pack_status: `{manual_review_pack_status}`",
        f"- bundle_complete: `{str(bundle_complete).lower()}`",
        f"- verdict: `{verdict}`",
        f"- recommended_next_action: `{next_action}`",
        "",
        "## Key warnings",
        "",
    ]
    if warnings:
        lines.extend([f"- {item}" for item in warnings])
    else:
        lines.append("- none")

    lines.extend(["", "## Key review-needed reasons", ""])
    if review_needed_reasons:
        lines.extend([f"- {item}" for item in review_needed_reasons])
    else:
        lines.append("- none")

    lines.extend(["", "## Missing artifacts", ""])
    if missing_artifacts:
        lines.extend([f"- {item}" for item in missing_artifacts])
    else:
        lines.append("- none")

    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rollout decision record from evidence bundle")
    parser.add_argument("--bundle-dir", default="rollout_evidence_bundle/smart_baseline_staging")
    parser.add_argument("--output-json", default="rollout_decision_record.json")
    parser.add_argument("--output-md", default="rollout_decision_record.md")
    args = parser.parse_args()

    record = build_decision_record(
        bundle_dir=Path(args.bundle_dir),
        output_json=Path(args.output_json),
        output_md=Path(args.output_md),
    )

    print(
        "rollout decision record summary: "
        f"verdict={record['verdict']}, "
        f"recommended_next_action={record['recommended_next_action']}, "
        f"final_readiness_status={record['final_readiness_status']}"
    )


if __name__ == "__main__":
    main()
