from __future__ import annotations

from tests import offline_kenlm_rerank_experiment as exp


def test_placeholder_scorer_is_deterministic() -> None:
    scorer = exp.DeterministicPlaceholderLMScorer()
    text = "сегодня будет по-русски"
    assert scorer.score(text) == scorer.score(text)


def test_run_dataset_experiment_report_shape(monkeypatch) -> None:
    cases = (exp.Case(input_text="кат", expected_clean_text="кот"),)

    monkeypatch.setattr(exp, "_run_standard_mode", lambda mode_label, cases, dictionary_source: ["кат"])
    monkeypatch.setattr(exp, "_offline_rerank_apply", lambda text, scorer, dictionary_source: ("кат", 0))

    report = exp.run_dataset_experiment(cases, dictionary_source="app/resources/ru_dictionary_v7.txt", scorer=exp.DeterministicPlaceholderLMScorer())

    assert report["candidate_source"] == "symspell_topk"
    assert report["comparison_targets"] == ["baseline", "current_apply", "offline_rerank"]
    assert "baseline" in report
    assert "current_apply" in report
    assert "offline_rerank" in report


def test_render_md_contains_research_markers() -> None:
    report = {
        "datasets": {
            "subset_benchmark": {
                "candidate_source": "symspell_topk",
                "top_k": 3,
                "sentence_scorer": "deterministic_placeholder_lm",
                "fail_closed_fallback": "no_apply",
                "comparison_targets": ["baseline", "current_apply", "offline_rerank"],
                "baseline": {
                    "exact_match_pass_count": 1,
                    "exact_match_pass_rate": 0.1,
                    "wrong_change": 0,
                    "unchanged_when_expected_change": 0,
                },
                "current_apply": {
                    "exact_match_pass_count": 1,
                    "exact_match_pass_rate": 0.1,
                    "wrong_change": 0,
                    "unchanged_when_expected_change": 0,
                },
                "offline_rerank": {
                    "exact_match_pass_count": 1,
                    "exact_match_pass_rate": 0.1,
                    "wrong_change": 0,
                    "unchanged_when_expected_change": 0,
                    "rerank_applied_edits": 0,
                },
            }
        }
    }
    md = exp._render_md(report)
    assert "Research-only offline track" in md
    assert "comparison_targets" in md
