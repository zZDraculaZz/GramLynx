from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_readiness_summary_marks_missing_and_not_ready_false_positive(tmp_path) -> None:
    cfg = tmp_path / "bad_profile.yml"
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

    out_json = tmp_path / "summary.json"
    out_md = tmp_path / "summary.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_readiness_summary.py"),
            "--config",
            str(cfg),
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
    assert payload["config_integrity_status"] == "drift_detected"
    assert payload["product_regression_status"] == "not_run"
    assert payload["delta_report_status"] in {"can_be_generated", "missing"}
    assert payload["manual_review_pack_status"] in {"can_be_generated", "missing"}
    assert payload["final_status"] in {"review_needed", "not_ready"}
    assert payload["final_status"] != "ready_for_review"

    md = out_md.read_text(encoding="utf-8")
    assert "# Smart Baseline Local Readiness Summary" in md
    assert "## Warnings" in md
    assert "## Review-needed reasons" in md

    assert "readiness summary:" in proc.stdout


def test_readiness_summary_ready_for_review_with_preexisting_artifacts(tmp_path) -> None:
    cfg = tmp_path / "good_profile.yml"
    cfg.write_text(
        """
rulepack:
  enable_candidate_generation_ru: true
  candidate_shadow_mode_ru: false
  candidate_backend: symspell
  dictionary_source_ru: app/resources/ru_dictionary_v7.txt
  max_candidates_ru: 3
  max_edit_distance_ru: 1
""",
        encoding="utf-8",
    )

    delta_jsonl = tmp_path / "product_delta_report.jsonl"
    delta_md = tmp_path / "product_delta_report.md"
    manual_jsonl = tmp_path / "manual_review_pack.jsonl"
    manual_md = tmp_path / "manual_review_pack.md"

    delta_jsonl.write_text('{"ok": true}\n', encoding="utf-8")
    delta_md.write_text("# delta\n", encoding="utf-8")
    manual_jsonl.write_text('{"ok": true}\n', encoding="utf-8")
    manual_md.write_text("# manual\n", encoding="utf-8")

    out_json = tmp_path / "summary.json"
    out_md = tmp_path / "summary.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_readiness_summary.py"),
            "--config",
            str(cfg),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
            "--run-product-regression",
            "--product-regression-test",
            str(Path(__file__).resolve().parent / "test_product_regression_pack.py"),
            "--delta-jsonl",
            str(delta_jsonl),
            "--delta-md",
            str(delta_md),
            "--manual-jsonl",
            str(manual_jsonl),
            "--manual-md",
            str(manual_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["config_integrity_status"] == "ok"
    assert payload["product_regression_status"] == "ok"
    assert payload["delta_report_status"] == "present"
    assert payload["manual_review_pack_status"] == "present"
    assert payload["final_status"] == "ready_for_review"

    md = out_md.read_text(encoding="utf-8")
    assert "final_status: `ready_for_review`" in md
    assert "## Available artifact paths" in md

    assert "readiness summary:" in proc.stdout
