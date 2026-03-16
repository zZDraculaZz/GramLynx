"""Offline context-aware rerank replay experiment for RuSpellGold datasets.

This utility is evaluation-only and does not modify production runtime behavior.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
from app.core.policy import get_policy
from app.core.protected_zones.detector import mask_protected_zones, restore_protected_zones
from app.core.stages.helpers import deterministic_spelling as ds
from app.core.v2.offline_eval import load_text_clean_jsonl
from tests import eval_ruspellgold_harness

DEFAULT_FULL_PUBLIC = Path("tests/cases/ruspellgold_full_public.jsonl")
DEFAULT_SUBSET = Path("tests/cases/ruspellgold_benchmark.jsonl")
DEFAULT_OUTPUT_JSON = Path("offline_context_rerank_replay_report.json")
DEFAULT_OUTPUT_MD = Path("offline_context_rerank_replay_report.md")
DEFAULT_DICTIONARY = "app/resources/ru_dictionary_v7.txt"

TOKEN_PATTERN = re.compile(r"\b[\w-]{2,}\b", flags=re.UNICODE)
FUNC_POS = {"PREP", "CONJ", "PRCL", "INTJ"}


@dataclass(frozen=True)
class Case:
    input_text: str
    expected_clean_text: str


@dataclass(frozen=True)
class CandidateView:
    term: str
    dist: int
    base_rank: int
    count: int


@dataclass(frozen=True)
class ReplayStats:
    generated: int = 0
    applied: int = 0
    not_applied: int = 0
    ambiguous: int = 0


@dataclass(frozen=True)
class CaseOutcome:
    input_text: str
    expected_clean_text: str
    output_text: str
    exact_match: bool
    wrong_change: bool
    unchanged_when_expected_change: bool
    candidate_generated_not_applied: bool
    unsafe_rejected: bool
    rollback_related: bool


def _load_cases(path: Path) -> tuple[Case, ...]:
    return tuple(Case(input_text=row.input_text, expected_clean_text=row.expected_clean_text) for row in load_text_clean_jsonl(path))


def _runtime_config(candidate_enabled: bool, shadow_mode: bool, backend: str, dictionary_source: str) -> str:
    return f"""
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  enable_candidate_generation_ru: {str(candidate_enabled).lower()}
  candidate_shadow_mode_ru: {str(shadow_mode).lower()}
  candidate_backend: {backend}
  max_candidates_ru: 3
  max_edit_distance_ru: 1
  dictionary_source_ru: {dictionary_source}
  typo_min_token_len: 2
  typo_map_smart_ru: {{}}
  no_touch_prefixes_ru:
    - "@"
    - "#"
"""


def _run_standard_mode(mode_label: str, cases: tuple[Case, ...], dictionary_source: str) -> tuple[list[CaseOutcome], dict[str, int | float]]:
    if mode_label == "baseline":
        candidate_enabled, shadow_mode, backend = False, False, "none"
    elif mode_label == "symspell_shadow":
        candidate_enabled, shadow_mode, backend = True, True, "symspell"
    elif mode_label == "symspell_apply":
        candidate_enabled, shadow_mode, backend = True, False, "symspell"
    else:
        raise ValueError(mode_label)

    if backend == "symspell" and importlib.util.find_spec("symspellpy") is None:
        raise RuntimeError("candidate backend unavailable: symspellpy is not installed")

    cfg_path = Path(tempfile.gettempdir()) / f"gramlynx_context_replay_{mode_label}.yml"
    cfg_path.write_text(
        _runtime_config(candidate_enabled, shadow_mode, backend, dictionary_source),
        encoding="utf-8",
    )

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg_path)
    reset_app_config_cache()

    outcomes: list[CaseOutcome] = []
    try:
        for index, case in enumerate(cases, start=1):
            orchestrator = Orchestrator(correlation_id=f"ctx-rerank-{mode_label}-{index}")
            with contextlib.redirect_stdout(io.StringIO()):
                output = orchestrator.clean(case.input_text, mode="smart")
            stats = orchestrator.last_run_stats
            outcomes.append(
                CaseOutcome(
                    input_text=case.input_text,
                    expected_clean_text=case.expected_clean_text,
                    output_text=output,
                    exact_match=output == case.expected_clean_text,
                    wrong_change=(output != case.expected_clean_text and output != case.input_text),
                    unchanged_when_expected_change=(case.input_text != case.expected_clean_text and output == case.input_text),
                    candidate_generated_not_applied=(
                        int(stats.get("candidate_generated_count", 0)) > 0 and int(stats.get("candidate_applied_count", 0)) == 0
                    ),
                    unsafe_rejected=int(stats.get("candidate_rejected_unsafe_candidate_count", 0)) > 0,
                    rollback_related=bool(stats.get("rollback_applied", False)),
                )
            )
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()

    return outcomes, _summary(outcomes)


def _parse_best(token: str, analyzer: Any | None) -> Any | None:
    if analyzer is None:
        return None
    parses = analyzer.parse(token)
    if not parses:
        return None
    return parses[0]


def _pos_and_lemma(token: str, analyzer: Any | None) -> tuple[str | None, str | None, int]:
    parse = _parse_best(token, analyzer)
    if parse is None:
        return None, None, 0
    tag = getattr(parse, "tag", None)
    pos = getattr(tag, "POS", None)
    lemma = getattr(parse, "normal_form", None)
    variants = len(analyzer.parse(token)) if analyzer is not None else 0
    return pos, lemma, variants


def _agreement_gain(candidate: str, left: str | None, right: str | None, analyzer: Any | None) -> float:
    if analyzer is None:
        return 0.0
    cand_parse = _parse_best(candidate, analyzer)
    if cand_parse is None:
        return 0.0

    cand_tag = getattr(cand_parse, "tag", None)
    cand_grams = set(getattr(cand_tag, "grammemes", ()) or ())
    gain = 0.0

    for neighbor in (left, right):
        if not neighbor:
            continue
        n_parse = _parse_best(neighbor, analyzer)
        if n_parse is None:
            continue
        n_tag = getattr(n_parse, "tag", None)
        n_grams = set(getattr(n_tag, "grammemes", ()) or ())
        if ("plur" in cand_grams and "plur" in n_grams) or ("sing" in cand_grams and "sing" in n_grams):
            gain += 0.15
        if any(case in cand_grams and case in n_grams for case in ("nomn", "gent", "datv", "accs", "ablt", "loct")):
            gain += 0.15
    return min(gain, 0.4)


def _score_candidate(
    token: str,
    candidate: CandidateView,
    left_token: str | None,
    right_token: str | None,
    analyzer: Any | None,
) -> float:
    score = 1.0
    score -= 0.35 * float(candidate.base_rank)
    score -= 0.30 * float(candidate.dist)

    tok_pos, tok_lemma, tok_variants = _pos_and_lemma(token, analyzer)
    cand_pos, cand_lemma, cand_variants = _pos_and_lemma(candidate.term, analyzer)

    if len(token) <= 3 or len(candidate.term) <= 3:
        score -= 0.35
    if tok_pos in FUNC_POS or cand_pos in FUNC_POS:
        score -= 0.45
    if tok_pos and cand_pos and tok_pos != cand_pos:
        score -= 0.35
    if tok_lemma and cand_lemma and tok_lemma != cand_lemma:
        score -= 0.20
    if cand_variants > tok_variants + 2:
        score -= 0.15

    score += _agreement_gain(candidate.term, left_token, right_token, analyzer)
    return score


def _topk_candidates(token: str, dictionary_source: str, max_k: int = 3, max_edit_distance: int = 1) -> list[CandidateView]:
    try:
        from symspellpy import Verbosity
    except Exception:
        return []

    symspell = ds._get_symspell(dictionary_source)
    if symspell is None:
        return []

    suggestions = symspell.lookup(
        token,
        Verbosity.CLOSEST,
        max_edit_distance=max_edit_distance,
        include_unknown=False,
        transfer_casing=False,
    )

    top: list[CandidateView] = []
    for index, suggestion in enumerate(suggestions):
        term = suggestion.term
        dist = int(suggestion.distance)
        if term == token or dist > max_edit_distance:
            continue
        if not ds._safe_candidate_token(term):
            continue
        top.append(CandidateView(term=term, dist=dist, base_rank=index, count=int(suggestion.count)))

    top.sort(key=lambda s: (s.dist, s.base_rank, -s.count, s.term))
    return top[:max(1, max_k)]


def _apply_replay(text: str, dictionary_source: str, margin_delta: float = 0.20, min_score: float = 0.05) -> tuple[str, ReplayStats]:
    masked, placeholders, _ = mask_protected_zones(text)
    analyzer = ds._get_morph_analyzer()
    policy = get_policy("smart")

    edits: list[tuple[int, int, str]] = []
    generated = 0
    applied = 0
    not_applied = 0
    ambiguous = 0

    matches = list(TOKEN_PATTERN.finditer(masked))
    for idx, match in enumerate(matches):
        token = match.group(0)
        if not ds._safe_ru_token(token):
            continue
        if ds._is_sensitive_wrapped_token(masked, match.start(), match.end(), ("@", "#")):
            continue

        left_token = matches[idx - 1].group(0) if idx > 0 else None
        right_token = matches[idx + 1].group(0) if idx + 1 < len(matches) else None

        candidates = _topk_candidates(token, dictionary_source=dictionary_source)
        if not candidates:
            continue

        generated += 1
        scored = [
            (
                cand,
                _score_candidate(token=token, candidate=cand, left_token=left_token, right_token=right_token, analyzer=analyzer),
            )
            for cand in candidates
        ]
        scored.sort(key=lambda item: (-item[1], item[0].dist, item[0].base_rank, item[0].term))

        best_cand, best_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else -999.0
        margin = best_score - second_score

        if best_score < min_score or margin < margin_delta:
            not_applied += 1
            if margin < margin_delta:
                ambiguous += 1
            continue
        if ds._is_plural_to_singular_drop(token, best_cand.term):
            not_applied += 1
            continue
        if analyzer is not None and ds._is_secondary_apply_guard_block_ru(token, best_cand.term, analyzer):
            not_applied += 1
            continue

        span_start = match.start()
        span_end = match.end()
        blocked = False
        for pz_match in re.finditer(r"⟦PZ\d+⟧", masked):
            if span_start < pz_match.end() + policy.pz_buffer_chars and span_end > pz_match.start() - policy.pz_buffer_chars:
                blocked = True
                break
        if blocked:
            not_applied += 1
            continue

        edits.append((span_start, span_end, best_cand.term))
        applied += 1

    if edits:
        out = []
        cursor = 0
        for start, end, repl in sorted(edits, key=lambda e: (e[0], e[1])):
            if start < cursor:
                continue
            out.append(masked[cursor:start])
            out.append(repl)
            cursor = end
        out.append(masked[cursor:])
        masked = "".join(out)

    restored = restore_protected_zones(masked, placeholders)
    return restored, ReplayStats(generated=generated, applied=applied, not_applied=not_applied, ambiguous=ambiguous)


def _run_replay_mode(cases: tuple[Case, ...], dictionary_source: str) -> tuple[list[CaseOutcome], dict[str, int | float]]:
    # Replay starts from safe baseline output and applies offline reranked candidates.
    baseline_outcomes, _ = _run_standard_mode("baseline", cases, dictionary_source)

    outcomes: list[CaseOutcome] = []
    for base in baseline_outcomes:
        replay_out, rstats = _apply_replay(base.output_text, dictionary_source=dictionary_source)
        outcomes.append(
            CaseOutcome(
                input_text=base.input_text,
                expected_clean_text=base.expected_clean_text,
                output_text=replay_out,
                exact_match=replay_out == base.expected_clean_text,
                wrong_change=(replay_out != base.expected_clean_text and replay_out != base.input_text),
                unchanged_when_expected_change=(base.input_text != base.expected_clean_text and replay_out == base.input_text),
                candidate_generated_not_applied=(rstats.generated > 0 and rstats.applied == 0),
                unsafe_rejected=False,
                rollback_related=False,
            )
        )
    return outcomes, _summary(outcomes)


def _summary(outcomes: list[CaseOutcome]) -> dict[str, int | float]:
    total = len(outcomes)
    exact = sum(1 for row in outcomes if row.exact_match)
    return {
        "total_cases": total,
        "exact_match_pass_count": exact,
        "exact_match_pass_rate": round(exact / total, 6) if total else 0.0,
        "wrong_change": sum(1 for row in outcomes if row.wrong_change),
        "unchanged_when_expected_change": sum(1 for row in outcomes if row.unchanged_when_expected_change),
        "candidate_generated_not_applied": sum(1 for row in outcomes if row.candidate_generated_not_applied),
        "unsafe_rejected": sum(1 for row in outcomes if row.unsafe_rejected),
        "rollback_related": sum(1 for row in outcomes if row.rollback_related),
    }


def _regresses_against_baseline(baseline: list[CaseOutcome], smart: list[CaseOutcome]) -> int:
    regressed = 0
    for b, s in zip(baseline, smart):
        if b.exact_match and not s.exact_match:
            regressed += 1
    return regressed


def _sample_deltas(apply_rows: list[CaseOutcome], replay_rows: list[CaseOutcome], limit: int = 8) -> dict[str, list[dict[str, str]]]:
    better: list[dict[str, str]] = []
    worse: list[dict[str, str]] = []
    for apply, replay in zip(apply_rows, replay_rows):
        if replay.exact_match and not apply.exact_match and len(better) < limit:
            better.append(
                {
                    "input_text": apply.input_text,
                    "expected_clean_text": apply.expected_clean_text,
                    "apply_output": apply.output_text,
                    "replay_output": replay.output_text,
                }
            )
        elif apply.exact_match and not replay.exact_match and len(worse) < limit:
            worse.append(
                {
                    "input_text": apply.input_text,
                    "expected_clean_text": apply.expected_clean_text,
                    "apply_output": apply.output_text,
                    "replay_output": replay.output_text,
                }
            )
        if len(better) >= limit and len(worse) >= limit:
            break
    return {"replay_beats_apply": better, "replay_worse_than_apply": worse}


def _heuristic_help_scope(samples: dict[str, list[dict[str, str]]]) -> str:
    texts = " ".join(item["input_text"] for item in samples["replay_beats_apply"])
    if not texts:
        return "no_clear_signal"
    short_hits = sum(1 for tok in re.findall(r"\b[А-Яа-яЁё]{1,3}\b", texts))
    return "mainly_short_or_function_words" if short_hits >= 5 else "broader_contextual_choices"


def run_experiment(dataset_path: Path, dictionary_source: str) -> dict[str, Any]:
    cases = _load_cases(dataset_path)
    baseline_rows, baseline = _run_standard_mode("baseline", cases, dictionary_source)
    shadow_rows, shadow = _run_standard_mode("symspell_shadow", cases, dictionary_source)
    apply_rows, apply = _run_standard_mode("symspell_apply", cases, dictionary_source)
    replay_rows, replay = _run_replay_mode(cases, dictionary_source)

    return {
        "dataset": str(dataset_path),
        "baseline": baseline,
        "symspell_shadow": shadow,
        "symspell_apply": {
            **apply,
            "smart_regresses_expected_match": _regresses_against_baseline(baseline_rows, apply_rows),
        },
        "offline_context_rerank_replay": {
            **replay,
            "smart_regresses_expected_match": _regresses_against_baseline(baseline_rows, replay_rows),
        },
        "samples": _sample_deltas(apply_rows, replay_rows),
        "help_scope": _heuristic_help_scope(_sample_deltas(apply_rows, replay_rows)),
    }


def _verdict(full_report: dict[str, Any]) -> str:
    apply = full_report["symspell_apply"]
    replay = full_report["offline_context_rerank_replay"]
    if (
        int(replay["wrong_change"]) < int(apply["wrong_change"])
        and float(replay["exact_match_pass_rate"]) >= float(apply["exact_match_pass_rate"])
    ):
        return "promising"
    if (
        int(replay["wrong_change"]) > int(apply["wrong_change"])
        and float(replay["exact_match_pass_rate"]) < float(apply["exact_match_pass_rate"])
    ):
        return "not_promising"
    return "inconclusive"


def _render_md(full_public: dict[str, Any], subset: dict[str, Any], verdict: str) -> str:
    def row(mode: str, payload: dict[str, Any]) -> str:
        return (
            f"| {mode} | {payload['exact_match_pass_count']} / {payload['exact_match_pass_rate']:.6f} | "
            f"{payload['wrong_change']} | {payload.get('smart_regresses_expected_match', '-')} | "
            f"{payload['candidate_generated_not_applied']} | {payload['unsafe_rejected']} | {payload['rollback_related']} |"
        )

    lines = [
        "# Offline Context Rerank Replay Report",
        "",
        "_Experiment only: not a production runtime path._",
        "",
        "## FULL PUBLIC",
        "",
        "| mode | exact_match | wrong_change | smart_regresses_expected_match | candidate_generated_not_applied | unsafe_rejected | rollback_related |",
        "|---|---:|---:|---:|---:|---:|---:|",
        row("baseline", full_public["baseline"]),
        row("symspell_shadow", full_public["symspell_shadow"]),
        row("symspell_apply", full_public["symspell_apply"]),
        row("offline_context_rerank_replay", full_public["offline_context_rerank_replay"]),
        "",
        "## SUBSET",
        "",
        "| mode | exact_match | wrong_change |",
        "|---|---:|---:|",
    ]
    for mode in ("baseline", "symspell_shadow", "symspell_apply", "offline_context_rerank_replay"):
        payload = subset[mode]
        lines.append(f"| {mode} | {payload['exact_match_pass_count']} / {payload['exact_match_pass_rate']:.6f} | {payload['wrong_change']} |")

    lines.extend(
        [
            "",
            "## Samples where replay beats current apply",
            "",
        ]
    )
    for sample in full_public["samples"]["replay_beats_apply"][:5]:
        lines.append(f"- input: `{sample['input_text']}`")
        lines.append(f"  - expected: `{sample['expected_clean_text']}`")
        lines.append(f"  - apply: `{sample['apply_output']}`")
        lines.append(f"  - replay: `{sample['replay_output']}`")

    lines.extend(
        [
            "",
            "## Samples where replay is worse",
            "",
        ]
    )
    for sample in full_public["samples"]["replay_worse_than_apply"][:5]:
        lines.append(f"- input: `{sample['input_text']}`")
        lines.append(f"  - expected: `{sample['expected_clean_text']}`")
        lines.append(f"  - apply: `{sample['apply_output']}`")
        lines.append(f"  - replay: `{sample['replay_output']}`")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- replay help scope: `{full_public['help_scope']}`",
            f"- verdict: **{verdict}**",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline context rerank replay (experiment only)")
    parser.add_argument("--full-public", type=Path, default=DEFAULT_FULL_PUBLIC)
    parser.add_argument("--subset", type=Path, default=DEFAULT_SUBSET)
    parser.add_argument("--dictionary-source", type=str, default=DEFAULT_DICTIONARY)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    eval_ruspellgold_harness._ensure_backend_available("symspell")

    full_public = run_experiment(args.full_public, args.dictionary_source)
    subset = run_experiment(args.subset, args.dictionary_source)
    verdict = _verdict(full_public)

    report = {
        "full_public": full_public,
        "subset": subset,
        "verdict": verdict,
        "experiment_only": True,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(_render_md(full_public, subset, verdict), encoding="utf-8")

    print(json.dumps({"verdict": verdict, "output_json": str(args.output_json), "output_md": str(args.output_md)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
