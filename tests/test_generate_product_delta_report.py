from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_generate_product_delta_report_on_small_sample(tmp_path) -> None:
    cases = tmp_path / "product_cases.yml"
    cases.write_text(
        """
smart:
  - category: chat
    input: "порусски"
    expected_clean_text: "по-русски"
  - category: neutral
    input: "текст без изменений"
    expected_clean_text: "текст без изменений"
""",
        encoding="utf-8",
    )

    safe_cfg = tmp_path / "safe.yml"
    safe_cfg.write_text(
        """
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s6_guardrails, s7_assemble]
rulepack:
  typo_map_smart_ru: {}
  enable_candidate_generation_ru: false
""",
        encoding="utf-8",
    )

    smart_cfg = tmp_path / "smart.yml"
    smart_cfg.write_text(
        """
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
rulepack:
  typo_map_smart:
    порусски: по-русски
  typo_map_smart_ru:
    порусски: по-русски
  enable_candidate_generation_ru: false
""",
        encoding="utf-8",
    )

    out_jsonl = tmp_path / "delta.jsonl"
    out_md = tmp_path / "delta.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_product_delta_report.py"),
            "--cases",
            str(cases),
            "--safe-config",
            str(safe_cfg),
            "--smart-config",
            str(smart_cfg),
            "--output-jsonl",
            str(out_jsonl),
            "--output-md",
            str(out_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert out_jsonl.exists()
    assert out_md.exists()

    rows = [json.loads(line) for line in out_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    assert all("input_text" in row for row in rows)
    assert all("output_safe_default" in row for row in rows)
    assert all("output_smart_baseline" in row for row in rows)
    assert all("changed_between_profiles" in row for row in rows)

    assert any(row["changed_between_profiles"] for row in rows)

    md = out_md.read_text(encoding="utf-8")
    assert "# Product Delta Report (safe default vs smart baseline)" in md
    assert "## Aggregates" in md
    assert "changed_only_in_smart_baseline" in md

    out = proc.stdout.strip()
    assert "product delta report summary:" in out
    assert "total_cases=" in out
