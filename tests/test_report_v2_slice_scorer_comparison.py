from __future__ import annotations

from pathlib import Path

from tests.report_v2_slice_scorer_comparison import format_compact_report, run_report


def _write_dictionary(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "привет 200",
                "дилемму 140",
                "сегодня 220",
                "завтра 210",
                "пожалуйста 250",
                "домой 180",
                "встреча 170",
                "тест 160",
                "акт 90",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_report_and_format_compact_output(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)

    payload = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
    )

    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10
    assert "decision_reason_counts_delta" in payload["delta"]

    text = format_compact_report(payload)
    assert "v2 slice scorer comparison summary:" in text
    assert "- total_cases: 10" in text
    assert "- summary_a:" in text
    assert "- summary_b:" in text
    assert "- delta:" in text
    assert "- decision_reason_counts_delta:" in text
