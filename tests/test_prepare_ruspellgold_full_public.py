from __future__ import annotations

import json
from pathlib import Path

from tests.prepare_ruspellgold_full_public import convert_raw_to_normalized


def test_convert_raw_to_normalized_success(tmp_path: Path) -> None:
    raw = tmp_path / "raw.json"
    raw.write_text(
        "\n".join(
            [
                json.dumps({"source": "севодня", "correction": "сегодня", "domain": "news"}, ensure_ascii=False),
                json.dumps({"source": "текст", "correction": "текст", "domain": "aranea"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.jsonl"

    summary = convert_raw_to_normalized(raw_path=raw, out_path=out)

    assert summary["rows_written"] == 2
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["input_text"] == "севодня"
    assert rows[0]["expected_clean_text"] == "сегодня"
    assert rows[0]["domain"] == "news"


def test_full_corpus_is_larger_than_subset() -> None:
    raw = Path("third_party/ruspellgold/raw/test.json")
    subset = Path("tests/cases/ruspellgold_benchmark.jsonl")

    raw_count = sum(1 for line in raw.read_text(encoding="utf-8").splitlines() if line.strip())
    subset_count = sum(1 for line in subset.read_text(encoding="utf-8").splitlines() if line.strip())

    assert raw_count > subset_count


def test_normalized_full_jsonl_is_valid_if_present() -> None:
    full_path = Path("tests/cases/ruspellgold_full_public.jsonl")
    if not full_path.exists():
        return

    rows = [json.loads(line) for line in full_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert len(rows) > 34
    first = rows[0]
    assert isinstance(first.get("input_text"), str)
    assert isinstance(first.get("expected_clean_text"), str)
