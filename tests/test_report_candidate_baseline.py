from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_report_candidate_baseline_script_outputs_expected_sections() -> None:
    script_path = Path(__file__).resolve().parent / "report_candidate_baseline.py"

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    output = proc.stdout

    assert "# Candidate Baseline Summary" in output
    assert "## Internal Harness" in output
    assert "## External Benchmark Harness" in output
    assert "## Verdict" in output
    assert "| mode | exact_match_pass_rate | candidate_generated_total | candidate_applied_total | candidate_rejected_no_result_total | candidate_ambiguous_total | rollback_total |" in output

    assert "baseline" in output
    assert "symspell_shadow" in output
    assert "symspell_apply" in output
    assert "quality lift present:" in output
    assert "safety stable:" in output

    assert "TODO" not in output
    assert "PLACEHOLDER" not in output
