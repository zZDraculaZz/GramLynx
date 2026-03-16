from __future__ import annotations

from pathlib import Path

import pytest

from app.core.v2 import is_kenlm_available
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
                "дом 80",
                "дома 100",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_report_and_format_compact_output_default_mode(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)

    payload, challenger_name = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
    )

    assert challenger_name == "ReverseRankScorer"
    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10
    assert "decision_reason_counts_delta" in payload["delta"]

    text = format_compact_report(payload, challenger_name=challenger_name)
    assert "v2 slice scorer comparison summary:" in text
    assert "- baseline_scorer: RankBasedScorer" in text
    assert "- challenger_scorer: ReverseRankScorer" in text
    assert "- total_cases: 10" in text
    assert "- summary_a:" in text
    assert "- summary_b:" in text
    assert "- delta:" in text
    assert "- decision_reason_counts_delta:" in text


KENLM_REQUIRED = pytest.mark.skipif(
    not is_kenlm_available(),
    reason="kenlm backend is not available in this environment",
)


@KENLM_REQUIRED
def test_run_report_kenlm_mode_runs_when_backend_and_model_available(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)

    arpa = tmp_path / "tiny.arpa"
    arpa.write_text(
        """\\data\\
ngram 1=5
ngram 2=4

\\1-grams:
-0.1 я -0.1
-0.1 дома -0.1
-0.1 дом -0.1
-0.1 сегодня -0.1
-0.1 тест -0.1

\\2-grams:
-0.01 я дома
-1.00 я дом
-0.05 сегодня тест
-0.40 сегодня дом

\\end\\
""",
        encoding="utf-8",
    )

    payload, challenger_name = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
        mode="kenlm",
        kenlm_model_path=arpa,
    )

    assert challenger_name == "KenLMScorer"
    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10
    assert isinstance(payload["delta"], dict)
    assert "decision_reason_counts_delta" in payload["delta"]
