from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_manual_review_pack_generator_on_small_sample(tmp_path) -> None:
    source = tmp_path / "sample_source.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "input_text": "севодня будет встреча",
                        "expected_clean_text": "сегодня будет встреча",
                        "source": "sample",
                        "category": "chat",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "input_text": "текст без изменений",
                        "expected_clean_text": "текст без изменений",
                        "source": "sample",
                        "category": "neutral",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_jsonl = tmp_path / "manual_review_pack.jsonl"
    out_md = tmp_path / "manual_review_pack.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "generate_manual_review_pack.py"),
            "--source-jsonl",
            str(source),
            "--config",
            "config.example.yml",
            "--limit",
            "20",
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
    assert rows, "expected non-empty high-signal selection"

    first = rows[0]
    assert "input_text" in first
    assert "output_text" in first
    assert "expected_clean_text" in first
    assert "why_in_pack" in first
    assert isinstance(first["why_in_pack"], list)
    assert first["why_in_pack"]
    assert "source" in first

    md = out_md.read_text(encoding="utf-8")
    assert "# Manual Review Pack" in md
    assert "## Cases" in md
    assert "Selection policy" in md

    out = proc.stdout.strip()
    assert "manual review pack summary:" in out
    assert "selected_high_signal_cases=" in out
