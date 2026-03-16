from __future__ import annotations

from pathlib import Path

import pytest

from app.core.v2 import is_kenlm_available
from research.context_rerank_v1.scorers.kenlm import KenLMScorer as ResearchKenLMScorer
from tests.report_v2_slice_scorer_comparison import (
    KENLM_MODEL_ENV,
    format_compact_report,
    get_kenlm_mode_blocker,
    run_report,
)


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

    payload, challenger_name, blocker = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
    )

    assert blocker is None
    assert challenger_name == "ReverseRankScorer"
    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10
    assert "decision_reason_counts_delta" in payload["delta"]

    text = format_compact_report(payload, requested_mode="deterministic", challenger_name=challenger_name, blocker=blocker)
    assert "v2 slice scorer comparison summary:" in text
    assert "- requested_mode: deterministic" in text
    assert "- baseline_scorer: RankBasedScorer" in text
    assert "- challenger_scorer: ReverseRankScorer" in text
    assert "- total_cases: 10" in text
    assert "- summary_a:" in text
    assert "- summary_b:" in text
    assert "- delta:" in text
    assert "- decision_reason_counts_delta:" in text




def test_run_report_heuristic_mode_runs_with_valid_structure(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)

    payload, challenger_name, blocker = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
        mode="heuristic",
    )

    assert blocker is None
    assert challenger_name == "ContextWindowHeuristicScorer"
    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10
    assert isinstance(payload["delta"], dict)

    text = format_compact_report(payload, requested_mode="heuristic", challenger_name=challenger_name, blocker=blocker)
    assert "- requested_mode: heuristic" in text
    assert "- challenger_scorer: ContextWindowHeuristicScorer" in text

def test_run_report_kenlm_mode_falls_back_with_clear_blocker(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)

    payload, challenger_name, blocker = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
        mode="kenlm",
    )

    if is_kenlm_available():
        assert blocker is not None
    else:
        assert challenger_name == "ReverseRankScorer"
        assert blocker is not None
    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10


KENLM_REQUIRED = pytest.mark.skipif(
    not is_kenlm_available(),
    reason="kenlm backend is not available in this environment",
)


@KENLM_REQUIRED
def test_get_kenlm_mode_blocker_reports_missing_model_path_in_kenlm_env() -> None:
    blocker = get_kenlm_mode_blocker(None)
    assert blocker is not None
    assert KENLM_MODEL_ENV in blocker


@KENLM_REQUIRED
def test_run_report_kenlm_mode_runs_when_backend_and_model_available(tmp_path: Path) -> None:
    dictionary = tmp_path / "slice_dict.txt"
    _write_dictionary(dictionary)

    arpa = tmp_path / "tiny.arpa"
    ResearchKenLMScorer.train_bigram_arpa(("всем привет", "иду домой", "наша встреча"), arpa)

    payload, challenger_name, blocker = run_report(
        cases_path=Path("tests/cases/v2_token_replay_slice_a.jsonl"),
        dictionary_path=dictionary,
        max_candidates=5,
        mode="kenlm",
        kenlm_model_path=arpa,
    )

    assert blocker is None
    assert challenger_name == "KenLMScorer"
    assert payload["summary_a"]["total_cases"] == 10
    assert payload["summary_b"]["total_cases"] == 10
    assert isinstance(payload["delta"], dict)
    assert "decision_reason_counts_delta" in payload["delta"]
