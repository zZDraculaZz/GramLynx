from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from research.context_rerank_v1.decision import fail_closed_pick
from research.context_rerank_v1.replay import (
    _apply_research_replay_v2,
    _combined_score,
    load_cases,
    load_config,
    make_scorer,
    run_replay,
)
from research.context_rerank_v1.report import render_markdown
from research.context_rerank_v1.scorers.kenlm import KenLMScorer
from research.context_rerank_v1.candidate_source import LargeLexiconCandidateSource


def _kenlm_backend_available() -> bool:
    return importlib.util.find_spec("kenlm") is not None


KENLM_REQUIRED = pytest.mark.skipif(
    not _kenlm_backend_available(),
    reason="kenlm backend is not available in this environment",
)


def test_scaffold_modules_import() -> None:
    from research.context_rerank_v1 import candidate_source as _candidate_source
    from research.context_rerank_v1.scorers import base as _base
    from research.context_rerank_v1.scorers import kenlm as _kenlm

    assert _candidate_source is not None
    assert _base is not None
    assert _kenlm is not None


def test_fail_closed_keeps_original_on_low_confidence() -> None:
    decision = fail_closed_pick(
        original_token="севодня",
        scored_candidates=(("сегодня", -100.0), ("свободня", -100.1)),
        min_margin=0.25,
        min_abs_score=-25.0,
    )
    assert decision.output_token == "севодня"
    assert decision.applied is False
    assert decision.reason == "low_abs_score"


def test_combined_score_deterministic() -> None:
    s1 = _combined_score(base_component=-1.3, kenlm_component=-4.2, alpha=0.9, beta=0.4)
    s2 = _combined_score(base_component=-1.3, kenlm_component=-4.2, alpha=0.9, beta=0.4)
    assert s1 == pytest.approx(s2)


@KENLM_REQUIRED
def test_kenlm_scorer_initializes_and_is_stable(tmp_path: Path) -> None:
    arpa = tmp_path / "tiny.arpa"
    KenLMScorer.train_bigram_arpa(("сегодня будет встреча", "это тест"), arpa)
    scorer = KenLMScorer(arpa)

    tokens = ("севодня", "будет", "встреча")
    s1 = scorer.score(tokens, 0, "сегодня")
    s2 = scorer.score(tokens, 0, "сегодня")
    assert isinstance(s1, float)
    assert s1 == pytest.approx(s2)


@KENLM_REQUIRED
def test_scorer_initializes_from_external_model_path(tmp_path: Path) -> None:
    arpa = tmp_path / "external.arpa"
    KenLMScorer.train_bigram_arpa(("привет мир", "сегодня встреча"), arpa)
    scorer = make_scorer({"scorer_type": "kenlm", "kenlm_model_path": str(arpa)})
    assert isinstance(scorer, KenLMScorer)


def test_make_scorer_requires_independent_source() -> None:
    with pytest.raises(ValueError, match="independent scorer source"):
        make_scorer({"scorer_type": "kenlm"})


@KENLM_REQUIRED
def test_beam_search_path_runs_and_preserves_fail_closed(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("сегодня\nбудет\nвстреча\n", encoding="utf-8")
    arpa = tmp_path / "m.arpa"
    KenLMScorer.train_bigram_arpa(("сегодня будет встреча",), arpa)
    scorer = KenLMScorer(arpa)
    source = LargeLexiconCandidateSource(dictionary, top_k=3)

    result = _apply_research_replay_v2(
        text="севодня будет встреча",
        candidate_source=source,
        scorer=scorer,
        min_margin=9999.0,
        min_abs_score=9999.0,
        alpha=1.0,
        beta=1.0,
        beam_width=3,
    )
    assert result["output_text"] == "севодня будет встреча"


@KENLM_REQUIRED
def test_replay_runs_with_pretrained_scorer_path(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("сегодня\nбудет\nвстреча\nтекст\nбез\nизменений\n", encoding="utf-8")

    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "input_text": "севодня будет встреча",
                        "expected_clean_text": "сегодня будет встреча",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "input_text": "текст без изменений",
                        "expected_clean_text": "текст без изменений",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    pretrained_arpa = tmp_path / "pretrained.arpa"
    KenLMScorer.train_bigram_arpa(("сегодня будет встреча", "текст без изменений"), pretrained_arpa)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "\n".join(
            [
                "top_k: 3",
                "min_margin: 0.2",
                "min_abs_score: -25.0",
                "combined_alpha: 1.0",
                "combined_beta: 1.0",
                "beam_width: 3",
                f"dictionary_source: {dictionary}",
                f"corpus_path: {corpus}",
                "scorer_type: kenlm",
                f"kenlm_model_path: {pretrained_arpa}",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_file)
    cases = load_cases(corpus)
    scorer = make_scorer(config)
    assert isinstance(scorer, KenLMScorer)

    summary = run_replay(config, cases)
    assert set(summary.keys()) == {
        "baseline",
        "current_apply",
        "research_replay_v1",
        "research_replay_v2",
        "buckets",
        "bucket_counts",
        "v2_score_contribution",
    }
    markdown = render_markdown(summary)
    assert "# Offline Context Rerank v1 Report" in markdown
    assert "## research_replay_v2" in markdown


@KENLM_REQUIRED
def test_replay_with_independent_corpus_path_runs(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("сегодня\nбудет\nвстреча\n", encoding="utf-8")
    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(
        json.dumps({"input_text": "севодня будет встреча", "expected_clean_text": "сегодня будет встреча"}, ensure_ascii=False),
        encoding="utf-8",
    )
    lm_corpus = tmp_path / "lm.txt"
    lm_corpus.write_text("сегодня будет встреча\n", encoding="utf-8")

    config = {
        "top_k": 3,
        "min_margin": 0.2,
        "min_abs_score": -25.0,
        "combined_alpha": 1.0,
        "combined_beta": 1.0,
        "beam_width": 3,
        "dictionary_source": str(dictionary),
        "corpus_path": str(corpus),
        "scorer_type": "kenlm",
        "kenlm_training_corpus_path": str(lm_corpus),
    }
    cases = load_cases(corpus)
    summary = run_replay(config, cases)
    assert summary["baseline"]["total_cases"] == 1


def test_candidate_source_supports_plain_dictionary_lines_with_symspell(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("# comment\nсегодня\nотдельного\n", encoding="utf-8")
    source = LargeLexiconCandidateSource(dictionary, top_k=5, max_edit_distance=3)

    suggestions = [c.term for c in source.top_k("отделного")]
    assert "отдельного" in suggestions


def test_candidate_source_normalizes_yo_variant(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("все\n", encoding="utf-8")
    source = LargeLexiconCandidateSource(dictionary, top_k=5, max_edit_distance=2)

    suggestions = [c.term for c in source.top_k("всёо")]
    assert "все" in suggestions
