from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_local_rollout_review_flow_smoke_end_to_end(tmp_path) -> None:
    cfg = tmp_path / "profile.yml"
    cfg.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_shadow_mode_ru: false
  candidate_backend: rapidfuzz
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
  max_candidates_ru: 3
  max_edit_distance_ru: 1
""",
        encoding="utf-8",
    )

    # 1) readiness summary
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    readiness_json = bundle_dir / "readiness_summary.json"
    readiness_md = bundle_dir / "readiness_summary.md"
    delta_jsonl = bundle_dir / "product_delta_report.jsonl"
    delta_md = bundle_dir / "product_delta_report.md"
    manual_jsonl = bundle_dir / "manual_review_pack.jsonl"
    manual_md = bundle_dir / "manual_review_pack.md"

    # Preseed delta/manual to keep smoke compact and deterministic.
    delta_jsonl.write_text('{"ok": true}\n', encoding="utf-8")
    delta_md.write_text("# delta\n", encoding="utf-8")
    manual_jsonl.write_text(
        json.dumps({"input_text": "sample", "why_in_pack": ["user_visible_change"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manual_md.write_text("# manual\n", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "tests/generate_readiness_summary.py",
            "--config",
            str(cfg),
            "--delta-jsonl",
            str(delta_jsonl),
            "--delta-md",
            str(delta_md),
            "--manual-jsonl",
            str(manual_jsonl),
            "--manual-md",
            str(manual_md),
            "--output-json",
            str(readiness_json),
            "--output-md",
            str(readiness_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    readiness = json.loads(readiness_json.read_text(encoding="utf-8"))
    manifest = {
        "profile_name": "smart_baseline_staging",
        "config_path": str(cfg),
        "available_artifacts": [
            "readiness_summary.json",
            "readiness_summary.md",
            "product_delta_report.jsonl",
            "product_delta_report.md",
            "manual_review_pack.jsonl",
            "manual_review_pack.md",
        ],
        "missing_artifacts": [],
        "final_readiness_status": readiness["final_status"],
        "warnings": list(readiness.get("warnings", [])),
        "bundle_complete": True,
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (bundle_dir / "INDEX.md").write_text("# Rollout Evidence Bundle\n", encoding="utf-8")

    # 3) rollout decision record
    decision_json = tmp_path / "decision.json"
    decision_md = tmp_path / "decision.md"
    subprocess.run(
        [
            sys.executable,
            "tests/generate_rollout_decision_record.py",
            "--bundle-dir",
            str(bundle_dir),
            "--output-json",
            str(decision_json),
            "--output-md",
            str(decision_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # 4) review adjudication record
    adjud_json = tmp_path / "adjudication.json"
    adjud_md = tmp_path / "adjudication.md"
    subprocess.run(
        [
            sys.executable,
            "tests/generate_review_adjudication_record.py",
            "--bundle-dir",
            str(bundle_dir),
            "--output-json",
            str(adjud_json),
            "--output-md",
            str(adjud_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # Artifacts exist across the full contour.
    assert readiness_json.exists()
    assert readiness_md.exists()
    assert (bundle_dir / "readiness_summary.json").exists()
    assert (bundle_dir / "readiness_summary.md").exists()
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "INDEX.md").exists()
    assert decision_json.exists()
    assert decision_md.exists()
    assert adjud_json.exists()
    assert adjud_md.exists()

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    decision = json.loads(decision_json.read_text(encoding="utf-8"))
    adjud = json.loads(adjud_json.read_text(encoding="utf-8"))

    # Conservative status alignment: drift/incomplete context must not become optimistic apply-ready.
    assert readiness["config_integrity_status"] in {"drift_detected", "fail"}
    assert manifest["final_readiness_status"] in {"review_needed", "not_ready"}
    assert decision["verdict"] != "eligible_for_controlled_apply"
    assert adjud["review_outcome"] != "approved_for_controlled_apply_review"
