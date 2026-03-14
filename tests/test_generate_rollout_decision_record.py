from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_decision_record_incomplete_bundle_is_not_optimistic(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)

    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "profile_name": "smart_baseline_staging",
                "config_path": "config.smart_baseline_staging.yml",
                "bundle_complete": False,
                "final_readiness_status": "review_needed",
                "warnings": ["bundle_incomplete"],
                "missing_artifacts": ["manual_review_pack.md"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out_json = tmp_path / "decision.json"
    out_md = tmp_path / "decision.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_rollout_decision_record.py"),
            "--bundle-dir",
            str(bundle),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["verdict"] == "hold_not_ready"
    assert payload["recommended_next_action"] == "regenerate_missing_artifacts"
    assert payload["verdict"] != "eligible_for_controlled_apply"

    md = out_md.read_text(encoding="utf-8")
    assert "# Smart Baseline Rollout Decision Record" in md
    assert "## Key warnings" in md
    assert "## Missing artifacts" in md

    assert "rollout decision record summary:" in proc.stdout


def test_decision_record_ready_bundle_can_be_apply_eligible(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)

    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "profile_name": "smart_baseline_staging",
                "config_path": "config.smart_baseline_staging.yml",
                "bundle_complete": True,
                "final_readiness_status": "ready_for_review",
                "warnings": [],
                "missing_artifacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (bundle / "readiness_summary.json").write_text(
        json.dumps(
            {
                "final_status": "ready_for_review",
                "config_integrity_status": "ok",
                "product_regression_status": "ok",
                "delta_report_status": "present",
                "manual_review_pack_status": "present",
                "warnings": [],
                "review_needed_reasons": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out_json = tmp_path / "decision.json"
    out_md = tmp_path / "decision.md"

    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_rollout_decision_record.py"),
            "--bundle-dir",
            str(bundle),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["verdict"] == "eligible_for_controlled_apply"
    assert payload["recommended_next_action"] == "proceed_to_controlled_apply_review"

    md = out_md.read_text(encoding="utf-8")
    assert "verdict: `eligible_for_controlled_apply`" in md
    assert "recommended_next_action: `proceed_to_controlled_apply_review`" in md
