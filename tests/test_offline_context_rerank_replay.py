from __future__ import annotations

from pathlib import Path

from tests import offline_context_rerank_replay as replay


def test_summary_has_required_sections() -> None:
    rows = [
        replay.CaseOutcome(
            input_text="a",
            expected_clean_text="b",
            output_text="b",
            exact_match=True,
            wrong_change=False,
            unchanged_when_expected_change=False,
            candidate_generated_not_applied=False,
            unsafe_rejected=False,
            rollback_related=False,
        ),
        replay.CaseOutcome(
            input_text="x",
            expected_clean_text="y",
            output_text="x",
            exact_match=False,
            wrong_change=False,
            unchanged_when_expected_change=True,
            candidate_generated_not_applied=True,
            unsafe_rejected=False,
            rollback_related=False,
        ),
    ]

    summary = replay._summary(rows)
    required = {
        "total_cases",
        "exact_match_pass_count",
        "exact_match_pass_rate",
        "wrong_change",
        "candidate_generated_not_applied",
        "unsafe_rejected",
        "rollback_related",
    }
    assert required.issubset(summary.keys())


def test_scoring_is_deterministic() -> None:
    cand = replay.CandidateView(term="кот", dist=1, base_rank=0, count=100)
    s1 = replay._score_candidate("кат", cand, left_token="мой", right_token="дом", analyzer=None)
    s2 = replay._score_candidate("кат", cand, left_token="мой", right_token="дом", analyzer=None)
    assert s1 == s2


def test_verdict_logic() -> None:
    full = {
        "symspell_apply": {"wrong_change": 10, "exact_match_pass_rate": 0.40},
        "offline_context_rerank_replay": {"wrong_change": 8, "exact_match_pass_rate": 0.40},
    }
    assert replay._verdict(full) == "promising"


def test_render_contains_key_headings() -> None:
    template = {
        "baseline": {
            "exact_match_pass_count": 1,
            "exact_match_pass_rate": 0.1,
            "wrong_change": 1,
            "smart_regresses_expected_match": 0,
            "candidate_generated_not_applied": 0,
            "unsafe_rejected": 0,
            "rollback_related": 0,
        },
        "symspell_shadow": {
            "exact_match_pass_count": 1,
            "exact_match_pass_rate": 0.1,
            "wrong_change": 1,
            "smart_regresses_expected_match": 0,
            "candidate_generated_not_applied": 0,
            "unsafe_rejected": 0,
            "rollback_related": 0,
        },
        "symspell_apply": {
            "exact_match_pass_count": 1,
            "exact_match_pass_rate": 0.1,
            "wrong_change": 1,
            "smart_regresses_expected_match": 0,
            "candidate_generated_not_applied": 0,
            "unsafe_rejected": 0,
            "rollback_related": 0,
        },
        "offline_context_rerank_replay": {
            "exact_match_pass_count": 1,
            "exact_match_pass_rate": 0.1,
            "wrong_change": 1,
            "smart_regresses_expected_match": 0,
            "candidate_generated_not_applied": 0,
            "unsafe_rejected": 0,
            "rollback_related": 0,
        },
        "samples": {"replay_beats_apply": [], "replay_worse_than_apply": []},
        "help_scope": "no_clear_signal",
    }
    md = replay._render_md(template, template, "inconclusive")
    assert "## FULL PUBLIC" in md
    assert "## SUBSET" in md
    assert "verdict" in md


def test_load_cases_reads_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    p.write_text('{"input_text":"тест","expected_clean_text":"тест"}\n', encoding="utf-8")
    cases = replay._load_cases(p)
    assert len(cases) == 1
