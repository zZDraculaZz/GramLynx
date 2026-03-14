"""Generate compact local readiness summary for smart-baseline rollout decisions."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

REQUIRED_BASELINE = {
    "candidate_backend": "symspell",
    "dictionary_source_ru": "app/resources/ru_dictionary_v7.txt",
    "max_candidates_ru": 3,
    "max_edit_distance_ru": 1,
}


def _read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid yaml structure")
    return payload


def _check_config_integrity(config_path: Path, profile_name: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not config_path.exists():
        return "fail", [f"config_missing:{config_path}"]

    try:
        payload = _read_yaml(config_path)
    except Exception:
        return "fail", [f"config_invalid_yaml:{config_path}"]

    rulepack = payload.get("rulepack")
    if not isinstance(rulepack, dict):
        return "fail", ["config_missing_rulepack"]

    for key, value in REQUIRED_BASELINE.items():
        if rulepack.get(key) != value:
            warnings.append(f"config_drift:{key}")

    if rulepack.get("enable_candidate_generation_ru") is not True:
        warnings.append("config_candidate_generation_not_enabled")

    if profile_name == "smart_baseline_staging" and rulepack.get("candidate_shadow_mode_ru") is not False:
        warnings.append("config_shadow_mode_unexpected_for_apply")
    if profile_name == "smart_baseline_shadow" and rulepack.get("candidate_shadow_mode_ru") is not True:
        warnings.append("config_shadow_mode_unexpected_for_shadow")

    return ("ok" if not warnings else "drift_detected", warnings)


def _run_pytest(test_path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_path)],
        capture_output=True,
        text=True,
    )
    ok = proc.returncode == 0
    return ok, (proc.stdout + proc.stderr).strip()


def _run_generator(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = proc.returncode == 0
    return ok, (proc.stdout + proc.stderr).strip()


def build_readiness_summary(
    profile_name: str,
    config_path: Path,
    output_json: Path,
    output_md: Path,
    run_product_regression: bool,
    product_regression_test_path: Path,
    delta_jsonl_path: Path,
    delta_md_path: Path,
    delta_generator_path: Path,
    generate_delta_if_missing: bool,
    manual_jsonl_path: Path,
    manual_md_path: Path,
    manual_generator_path: Path,
    generate_manual_if_missing: bool,
) -> dict[str, object]:
    warnings: list[str] = []
    review_needed_reasons: list[str] = []
    artifacts: dict[str, str] = {}

    config_status, config_warnings = _check_config_integrity(config_path, profile_name)
    warnings.extend(config_warnings)

    if run_product_regression:
        ok, details = _run_pytest(product_regression_test_path)
        product_regression_status = "ok" if ok else "failed"
        if not ok:
            warnings.append("product_regression_failed")
            review_needed_reasons.append("product_regression_failed")
        artifacts["product_regression_test"] = str(product_regression_test_path)
        artifacts["product_regression_run_log_excerpt"] = details[:500]
    else:
        product_regression_status = "not_run"
        warnings.append("product_regression_not_run")
        review_needed_reasons.append("product_regression_not_run")

    # delta report signal
    if delta_jsonl_path.exists() and delta_md_path.exists():
        delta_status = "present"
        artifacts["delta_jsonl"] = str(delta_jsonl_path)
        artifacts["delta_md"] = str(delta_md_path)
    elif generate_delta_if_missing and delta_generator_path.exists():
        ok, details = _run_generator(
            [
                sys.executable,
                str(delta_generator_path),
                "--safe-config",
                "config.example.yml",
                "--smart-config",
                str(config_path),
                "--output-jsonl",
                str(delta_jsonl_path),
                "--output-md",
                str(delta_md_path),
            ]
        )
        if ok and delta_jsonl_path.exists() and delta_md_path.exists():
            delta_status = "generated"
            artifacts["delta_jsonl"] = str(delta_jsonl_path)
            artifacts["delta_md"] = str(delta_md_path)
        else:
            delta_status = "missing"
            warnings.append("delta_report_generate_failed")
            review_needed_reasons.append("delta_report_missing")
            artifacts["delta_generate_log_excerpt"] = details[:500]
    elif delta_generator_path.exists():
        delta_status = "can_be_generated"
        warnings.append("delta_report_missing")
        review_needed_reasons.append("delta_report_missing")
    else:
        delta_status = "missing"
        warnings.append("delta_report_generator_missing")
        review_needed_reasons.append("delta_report_missing")

    # manual review pack signal
    if manual_jsonl_path.exists() and manual_md_path.exists():
        manual_status = "present"
        artifacts["manual_review_jsonl"] = str(manual_jsonl_path)
        artifacts["manual_review_md"] = str(manual_md_path)
    elif generate_manual_if_missing and manual_generator_path.exists():
        ok, details = _run_generator(
            [
                sys.executable,
                str(manual_generator_path),
                "--config",
                str(config_path),
                "--output-jsonl",
                str(manual_jsonl_path),
                "--output-md",
                str(manual_md_path),
            ]
        )
        if ok and manual_jsonl_path.exists() and manual_md_path.exists():
            manual_status = "generated"
            artifacts["manual_review_jsonl"] = str(manual_jsonl_path)
            artifacts["manual_review_md"] = str(manual_md_path)
        else:
            manual_status = "missing"
            warnings.append("manual_review_pack_generate_failed")
            review_needed_reasons.append("manual_review_pack_missing")
            artifacts["manual_generate_log_excerpt"] = details[:500]
    elif manual_generator_path.exists():
        manual_status = "can_be_generated"
        warnings.append("manual_review_pack_missing")
        review_needed_reasons.append("manual_review_pack_missing")
    else:
        manual_status = "missing"
        warnings.append("manual_review_pack_generator_missing")
        review_needed_reasons.append("manual_review_pack_missing")

    if config_status == "fail" or product_regression_status == "failed":
        final_status = "not_ready"
    elif (
        config_status == "ok"
        and product_regression_status == "ok"
        and delta_status in {"present", "generated"}
        and manual_status in {"present", "generated"}
    ):
        final_status = "ready_for_review"
    else:
        final_status = "review_needed"

    summary: dict[str, object] = {
        "profile_name": profile_name,
        "config_path": str(config_path),
        "config_integrity_status": config_status,
        "product_regression_status": product_regression_status,
        "delta_report_status": delta_status,
        "manual_review_pack_status": manual_status,
        "available_artifact_paths": artifacts,
        "warnings": sorted(set(warnings)),
        "review_needed_reasons": sorted(set(review_needed_reasons)),
        "final_status": final_status,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Smart Baseline Local Readiness Summary",
        "",
        f"- profile_name: `{profile_name}`",
        f"- config_path: `{config_path}`",
        f"- config_integrity_status: `{config_status}`",
        f"- product_regression_status: `{product_regression_status}`",
        f"- delta_report_status: `{delta_status}`",
        f"- manual_review_pack_status: `{manual_status}`",
        f"- final_status: `{final_status}`",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend([f"- {w}" for w in sorted(set(warnings))])
    else:
        lines.append("- none")

    lines.extend(["", "## Review-needed reasons", ""])
    if review_needed_reasons:
        lines.extend([f"- {r}" for r in sorted(set(review_needed_reasons))])
    else:
        lines.append("- none")

    lines.extend(["", "## Available artifact paths", ""])
    if artifacts:
        for key in sorted(artifacts):
            lines.append(f"- {key}: `{artifacts[key]}`")
    else:
        lines.append("- none")

    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local readiness summary for smart baseline")
    parser.add_argument("--profile-name", default="smart_baseline_staging")
    parser.add_argument("--config", default="config.smart_baseline_staging.yml")
    parser.add_argument("--output-json", default="smart_baseline_readiness_summary.json")
    parser.add_argument("--output-md", default="smart_baseline_readiness_summary.md")

    parser.add_argument("--run-product-regression", action="store_true")
    parser.add_argument("--product-regression-test", default="tests/test_product_regression_pack.py")

    parser.add_argument("--delta-jsonl", default="product_delta_report.jsonl")
    parser.add_argument("--delta-md", default="product_delta_report.md")
    parser.add_argument("--delta-generator", default="tests/generate_product_delta_report.py")
    parser.add_argument("--generate-delta-if-missing", action="store_true")

    parser.add_argument("--manual-jsonl", default="manual_review_pack.jsonl")
    parser.add_argument("--manual-md", default="manual_review_pack.md")
    parser.add_argument("--manual-generator", default="tests/generate_manual_review_pack.py")
    parser.add_argument("--generate-manual-if-missing", action="store_true")

    args = parser.parse_args()

    summary = build_readiness_summary(
        profile_name=args.profile_name,
        config_path=Path(args.config),
        output_json=Path(args.output_json),
        output_md=Path(args.output_md),
        run_product_regression=args.run_product_regression,
        product_regression_test_path=Path(args.product_regression_test),
        delta_jsonl_path=Path(args.delta_jsonl),
        delta_md_path=Path(args.delta_md),
        delta_generator_path=Path(args.delta_generator),
        generate_delta_if_missing=args.generate_delta_if_missing,
        manual_jsonl_path=Path(args.manual_jsonl),
        manual_md_path=Path(args.manual_md),
        manual_generator_path=Path(args.manual_generator),
        generate_manual_if_missing=args.generate_manual_if_missing,
    )

    print(
        "readiness summary: "
        f"profile={summary['profile_name']}, "
        f"config_integrity_status={summary['config_integrity_status']}, "
        f"product_regression_status={summary['product_regression_status']}, "
        f"delta_report_status={summary['delta_report_status']}, "
        f"manual_review_pack_status={summary['manual_review_pack_status']}, "
        f"final_status={summary['final_status']}"
    )


if __name__ == "__main__":
    main()
