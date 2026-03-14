from __future__ import annotations

import json
from pathlib import Path

from tests.generate_usefulness_showcase import generate_usefulness_showcase


def test_generate_usefulness_showcase_sections_and_content(tmp_path: Path) -> None:
    delta = tmp_path / "delta.jsonl"
    rows = [
        {
            "input_text": "севодня буду позже",
            "expected_clean_text": "сегодня буду позже",
            "output_safe_default": "севодня буду позже",
            "output_smart_baseline": "сегодня буду позже",
            "changed_between_profiles": True,
            "smart_matches_expected": True,
            "safe_matches_expected": False,
            "user_visible_delta_reason": "smart_improves_expected_match",
            "category": "chat/messenger",
        },
        {
            "input_text": "имхо норм",
            "expected_clean_text": "имхо норм",
            "output_safe_default": "имхо норм",
            "output_smart_baseline": "имхо норм",
            "changed_between_profiles": False,
            "smart_matches_expected": True,
            "safe_matches_expected": True,
            "user_visible_delta_reason": None,
            "category": "chat/messenger",
        },
        {
            "input_text": "пример",
            "expected_clean_text": "пример",
            "output_safe_default": "пример",
            "output_smart_baseline": "пример!",
            "changed_between_profiles": True,
            "smart_matches_expected": False,
            "safe_matches_expected": True,
            "user_visible_delta_reason": "smart_regresses_expected_match",
            "category": "review",
        },
    ]
    with delta.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    out = tmp_path / "showcase.md"
    summary = generate_usefulness_showcase(delta_jsonl=delta, output_md=out)

    assert summary["total_rows"] == 3
    assert summary["improvement_cases"] >= 1
    assert summary["preservation_cases"] >= 1
    assert summary["caution_cases"] >= 1

    content = out.read_text(encoding="utf-8")
    assert "## Что сервис улучшает" in content
    assert "## Что сервис специально не трогает" in content
    assert "## Какие кейсы требуют осторожности/ручного review" in content
    assert "output_safe_default" in content
    assert "output_smart_baseline" in content
