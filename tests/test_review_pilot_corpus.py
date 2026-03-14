from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests import review_pilot_corpus as pilot


def test_pilot_schema_validation_fail_closed_on_invalid_row(tmp_path) -> None:
    corpus = tmp_path / "broken.jsonl"
    corpus.write_text('{"input_text": 123}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid input_text"):
        pilot._load_cases(corpus)


def test_pilot_schema_validation_fail_closed_on_unknown_keys(tmp_path) -> None:
    corpus = tmp_path / "broken_unknown.jsonl"
    corpus.write_text('{"input_text":"ok","extra":"bad"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid pilot schema"):
        pilot._load_cases(corpus)


def test_pilot_fail_closed_on_missing_corpus_path(tmp_path) -> None:
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(FileNotFoundError, match="pilot corpus not found"):
        pilot._load_cases(missing)


def test_pilot_report_generation_and_stdout_summary(tmp_path) -> None:
    corpus = tmp_path / "pilot.jsonl"
    corpus.write_text(
        '\n'.join(
            [
                json.dumps({"input_text": "севодня будет встреча", "expected_clean_text": "сегодня будет встреча"}, ensure_ascii=False),
                json.dumps({"input_text": "текст без изменений", "expected_clean_text": "текст без изменений"}, ensure_ascii=False),
            ]
        )
        + '\n',
        encoding="utf-8",
    )
    report = tmp_path / "pilot_review_report.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "review_pilot_corpus.py"),
            "--corpus",
            str(corpus),
            "--report",
            str(report),
            "--config",
            "config.smart_baseline_staging.yml",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert report.exists()
    output = proc.stdout.strip()
    assert "pilot review summary:" in output
    assert "total_cases=" in output
    assert "changed_count=" in output
    assert "rollback_total=" in output
    assert "unsafe_total=" in output
    assert "PLACEHOLDER" not in output

    report_text = report.read_text(encoding="utf-8")
    assert "# Pilot Manual Review Report" in report_text
    assert "## Cases" in report_text
    assert "## Summary" in report_text
    assert "PLACEHOLDER" not in report_text
    assert "TODO" not in report_text
