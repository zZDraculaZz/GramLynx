from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_review_adjudication_incomplete_inputs_are_not_optimistic(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "profile_name": "smart_baseline_staging",
                "config_path": "config.smart_baseline_staging.yml",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out_json = tmp_path / "review_adjudication.json"
    out_md = tmp_path / "review_adjudication.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_review_adjudication_record.py"),
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
    assert payload["review_outcome"] == "blocked"
    assert payload["recommended_follow_up"] == "inspect_blocking_cases"
    assert payload["review_outcome"] != "approved_for_controlled_apply_review"

    md = out_md.read_text(encoding="utf-8")
    assert "# Smart Baseline Review Adjudication Record" in md
    assert "## Reviewer notes" in md
    assert "## Interpretation" in md

    assert "review adjudication summary:" in proc.stdout


def test_review_adjudication_can_be_approved_when_all_reviewed(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "profile_name": "smart_baseline_staging",
                "config_path": "config.smart_baseline_staging.yml",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (bundle / "manual_review_pack.jsonl").write_text(
        '\n'.join(
            [
                json.dumps({"input_text": "a", "why_in_pack": ["user_visible_change"]}, ensure_ascii=False),
                json.dumps({"input_text": "b", "why_in_pack": ["candidate_ambiguous"]}, ensure_ascii=False),
            ]
        )
        + '\n',
        encoding="utf-8",
    )

    out_json = tmp_path / "review_adjudication.json"
    out_md = tmp_path / "review_adjudication.md"

    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_review_adjudication_record.py"),
            "--bundle-dir",
            str(bundle),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
            "--accepted-case-count",
            "2",
            "--reviewer-notes",
            "review complete",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["review_candidate_count"] == 2
    assert payload["reviewed_case_count"] == 2
    assert payload["unresolved_case_count"] == 0
    assert payload["review_outcome"] == "approved_for_controlled_apply_review"
    assert payload["recommended_follow_up"] == "proceed_to_controlled_apply_review"

    md = out_md.read_text(encoding="utf-8")
    assert "review_outcome: `approved_for_controlled_apply_review`" in md
