"""Convert vendored raw RuSpellGold test corpus into harness-compatible JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RAW_DEFAULT = Path("third_party/ruspellgold/raw/test.json")
OUT_DEFAULT = Path("tests/cases/ruspellgold_full_public.jsonl")


def convert_raw_to_normalized(raw_path: Path, out_path: Path) -> dict[str, int]:
    if not raw_path.exists():
        raise FileNotFoundError(f"raw RuSpellGold file not found: {raw_path}")

    raw_lines = raw_path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, str]] = []

    for index, raw in enumerate(raw_lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid raw JSON at line {index}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"invalid raw row type at line {index}")

        source = payload.get("source")
        correction = payload.get("correction")
        domain = payload.get("domain")

        if not isinstance(source, str) or not isinstance(correction, str):
            raise ValueError(f"invalid schema at line {index}: source/correction must be strings")
        if not source:
            raise ValueError(f"empty source at line {index}")
        if domain is not None and not isinstance(domain, str):
            raise ValueError(f"invalid domain at line {index}")

        row = {
            "input_text": source,
            "expected_clean_text": correction,
        }
        if isinstance(domain, str):
            row["domain"] = domain
        rows.append(row)

    if not rows:
        raise ValueError("raw RuSpellGold file is empty after parsing")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"rows_written": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert local raw RuSpellGold corpus to harness JSONL")
    parser.add_argument("--raw", default=str(RAW_DEFAULT), help="Path to raw RuSpellGold JSONL")
    parser.add_argument("--out", default=str(OUT_DEFAULT), help="Path to normalized output JSONL")
    args = parser.parse_args()

    summary = convert_raw_to_normalized(raw_path=Path(args.raw), out_path=Path(args.out))
    print(f"converted_ruspellgold rows_written={summary['rows_written']} out={args.out}")


if __name__ == "__main__":
    main()
