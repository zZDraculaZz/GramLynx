from __future__ import annotations

import importlib.util
import json
import os
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
from research.context_rerank_v1.scorers.encoder_ranker import EncoderRankerScorer, encoder_backend_available
from research.context_rerank_v1.candidate_source import LargeLexiconCandidateSource


def _kenlm_backend_available() -> bool:
    return importlib.util.find_spec("kenlm") is not None


KENLM_REQUIRED = pytest.mark.skipif(
    not _kenlm_backend_available(),
    reason="kenlm backend is not available in this environment",
)


ENCODER_REQUIRED = pytest.mark.skipif(
    not encoder_backend_available(),
    reason="encoder_ranker backend is not available in this environment",
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


def test_encoder_ranker_factory_requires_model_name() -> None:
    with pytest.raises(ValueError, match="encoder_model_name_or_path"):
        make_scorer({"scorer_type": "encoder_ranker"})


def test_encoder_ranker_factory_fails_fast_when_backend_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("research.context_rerank_v1.scorers.encoder_ranker.encoder_backend_available", lambda: False)
    with pytest.raises(RuntimeError, match="encoder_ranker backend is not available"):
        make_scorer(
            {
                "scorer_type": "encoder_ranker",
                "encoder_model_name_or_path": "ai-forever/ruBert-base",
                "batch_size": 2,
                "max_seq_len": 64,
                "device": "cpu",
                "local_files_only": True,
            }
        )


@ENCODER_REQUIRED
def test_encoder_ranker_replay_smoke_if_model_path_provided(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_name = os.environ.get("GRAMLYNX_ENCODER_MODEL_PATH")
    if not model_name:
        pytest.skip("GRAMLYNX_ENCODER_MODEL_PATH is not set")

    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("сегодня\nбудет\nвстреча\n", encoding="utf-8")
    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(
        json.dumps({"input_text": "севодня будет встреча", "expected_clean_text": "сегодня будет встреча"}, ensure_ascii=False),
        encoding="utf-8",
    )

    config = {
        "top_k": 3,
        "min_margin": 0.2,
        "min_abs_score": -25.0,
        "combined_alpha": 1.0,
        "combined_beta": 1.0,
        "beam_width": 2,
        "dictionary_source": str(dictionary),
        "corpus_path": str(corpus),
        "scorer_type": "encoder_ranker",
        "encoder_model_name_or_path": model_name,
        "batch_size": 1,
        "max_seq_len": 64,
        "device": "cpu",
        "local_files_only": True,
    }
    cases = load_cases(corpus)
    scorer = make_scorer(config)
    assert isinstance(scorer, EncoderRankerScorer)

    summary = run_replay(config, cases)
    assert summary["baseline"]["total_cases"] == 1


def test_first_encoder_comparison_reports_blocker_when_backend_missing(tmp_path: Path) -> None:
    from research.context_rerank_v1.first_encoder_comparison import main as comparison_main

    output = tmp_path / "comparison.json"
    argv = [
        "prog",
        "--output-json",
        str(output),
    ]

    import sys

    old_argv = sys.argv
    try:
        sys.argv = argv
        comparison_main()
    finally:
        sys.argv = old_argv

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] in {"blocked", "ok"}
    if payload["status"] == "blocked":
        assert any(hint in payload["blocker"] for hint in ("torch", "model load/run", "research-encoder"))


def test_encoder_backend_blocker_message_smoke() -> None:
    from research.context_rerank_v1.encoder_setup import encoder_backend_blocker_message, encoder_backend_ready

    msg = encoder_backend_blocker_message()
    if encoder_backend_ready():
        assert msg == ""
    else:
        assert "research-encoder" in msg


def test_first_encoder_comparison_reports_runtime_blocker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from research.context_rerank_v1 import first_encoder_comparison as comparison

    monkeypatch.setattr(comparison, "encoder_backend_ready", lambda: True)

    def _boom(_: Path) -> dict[str, object]:
        raise OSError("403 Forbidden")

    monkeypatch.setattr(comparison, "_run_encoder_report", _boom)

    output = tmp_path / "comparison_runtime_blocked.json"
    argv = ["prog", "--output-json", str(output)]

    import sys

    old_argv = sys.argv
    try:
        sys.argv = argv
        comparison.main()
    finally:
        sys.argv = old_argv

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert "model load/run" in payload["blocker"]


def test_root_cause_audit_smoke(tmp_path: Path) -> None:
    from research.context_rerank_v1.root_cause_audit import run_audit

    out = tmp_path / "root_cause_audit.json"
    payload = run_audit(out)
    assert out.exists()
    assert "full_public" in payload
    assert "candidate_source_failure_slices" in payload["full_public"]


def test_candidate_source_retrieval_normalization_adds_yo_variant(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("ещё\n", encoding="utf-8")

    legacy = LargeLexiconCandidateSource(dictionary, top_k=5, max_edit_distance=2, enable_retrieval_normalization=False)
    improved = LargeLexiconCandidateSource(dictionary, top_k=5, max_edit_distance=2, enable_retrieval_normalization=True)

    legacy_terms = [c.term for c in legacy.top_k("еще")]
    improved_terms = [c.term for c in improved.top_k("еще")]

    assert "ещё" not in legacy_terms
    assert "ещё" in improved_terms


def test_candidate_source_retrieval_normalization_hyphen_variant(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("из-за\n", encoding="utf-8")

    legacy = LargeLexiconCandidateSource(dictionary, top_k=5, max_edit_distance=2, enable_retrieval_normalization=False)
    improved = LargeLexiconCandidateSource(dictionary, top_k=5, max_edit_distance=2, enable_retrieval_normalization=True)

    legacy_terms = [c.term for c in legacy.top_k("(изза)")]
    improved_terms = [c.term for c in improved.top_k("(изза)")]

    assert "из-за" not in legacy_terms
    assert "из-за" in improved_terms


@KENLM_REQUIRED
def test_run_replay_current_apply_cache_roundtrip(tmp_path: Path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("сегодня\nбудет\nвстреча\n", encoding="utf-8")
    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(
        json.dumps({"input_text": "севодня будет встреча", "expected_clean_text": "сегодня будет встреча"}, ensure_ascii=False),
        encoding="utf-8",
    )
    lm_corpus = tmp_path / "lm.txt"
    lm_corpus.write_text("сегодня будет встреча\n", encoding="utf-8")
    cache = tmp_path / "current_apply_cache.json"

    cfg = {
        "top_k": 3,
        "min_margin": 0.2,
        "min_abs_score": -25.0,
        "combined_alpha": 1.0,
        "combined_beta": 1.0,
        "beam_width": 2,
        "dictionary_source": str(dictionary),
        "corpus_path": str(corpus),
        "scorer_type": "kenlm",
        "kenlm_training_corpus_path": str(lm_corpus),
        "current_apply_cache_path": str(cache),
    }
    cases = load_cases(corpus)
    first = run_replay(cfg, cases)
    second = run_replay(cfg, cases)
    assert cache.exists()
    assert first["research_replay_v2"]["total_cases"] == second["research_replay_v2"]["total_cases"]
