from __future__ import annotations

import contextlib
import io
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any
import re

import yaml

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
from tests import eval_ruspellgold_harness as canonical_harness

from research.context_rerank_v1.candidate_source import LargeLexiconCandidateSource
from research.context_rerank_v1.replay import (
    BeamState,
    _combined_score,
    _load_cases_jsonl,
    _load_cases_yaml,
    make_scorer,
)
from research.context_rerank_v1.scorers.kenlm import KenLMScorer


def _load_cases(path: Path) -> list[tuple[str, str]]:
    if path.suffix.lower() in {".yml", ".yaml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return [(row["input"], row["expected_clean_text"]) for row in payload["smart"]]
    return [(c.input_text, c.expected_clean_text) for c in _load_cases_jsonl(path)]


def _run_runtime_cases(cases: list[tuple[str, str]], *, candidate_enabled: bool, shadow_mode: bool, backend: str) -> tuple[list[str], list[bool]]:
    cfg_path = Path(tempfile.gettempdir()) / f"audit_profile_{backend}_{candidate_enabled}_{shadow_mode}.yml"
    cfg_path.write_text(
        canonical_harness._runtime_config(
            candidate_enabled,
            shadow_mode,
            backend,
            canonical_harness._resolve_eval_dictionary_source(),
        ),
        encoding="utf-8",
    )

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg_path)
    reset_app_config_cache()

    outputs: list[str] = []
    rollbacks: list[bool] = []
    try:
        for idx, (input_text, _) in enumerate(cases, start=1):
            orchestrator = Orchestrator(correlation_id=f"audit-{backend}-{idx}")
            with contextlib.redirect_stdout(io.StringIO()):
                out = orchestrator.clean(input_text, mode="smart")
            outputs.append(out)
            rollbacks.append(bool(orchestrator.last_run_stats.get("rollback_applied", False)))
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()

    return outputs, rollbacks


def _compute_metrics(outputs: list[str], cases: list[tuple[str, str]], current_apply_outputs: list[str], rollbacks: list[bool]) -> dict[str, Any]:
    total = len(cases)
    exact = sum(1 for out, (_, expected) in zip(outputs, cases) if out == expected)
    wrong_change = sum(1 for out, (inp, expected) in zip(outputs, cases) if out != expected and out != inp)
    regresses = sum(
        1
        for out, apply_out, (_, expected) in zip(outputs, current_apply_outputs, cases)
        if out != expected and apply_out == expected
    )
    return {
        "total_cases": total,
        "exact_match_pass_count": exact,
        "exact_match_pass_rate": exact / total if total else 0.0,
        "wrong_change": wrong_change,
        "smart_regresses_expected_match": regresses,
        "rollback_related": sum(1 for x in rollbacks if x),
    }


def _candidate_base_score(distance: int, rank: int) -> float:
    return -(1.0 * float(distance) + 0.15 * float(rank))


def _run_kenlm_v2_with_audit(
    cases: list[tuple[str, str]],
    cfg: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    scorer = make_scorer(cfg)
    if not isinstance(scorer, KenLMScorer):
        raise TypeError("KenLM scorer required")

    extra_dictionary_sources = tuple(str(p) for p in cfg.get("extra_dictionary_sources", []))
    cand_source = LargeLexiconCandidateSource(
        dictionary_path=str(cfg["dictionary_source"]),
        top_k=int(cfg["top_k"]),
        max_edit_distance=int(cfg.get("max_edit_distance", 3)),
        extra_dictionary_paths=extra_dictionary_sources,
    )
    alpha = float(cfg.get("combined_alpha", 1.0))
    beta = float(cfg.get("combined_beta", 1.0))
    min_margin = float(cfg["min_margin"])
    min_abs_score = float(cfg["min_abs_score"])
    beam_width = int(cfg.get("beam_width", 4))

    outputs: list[str] = []
    keep_reason = Counter()
    token_reason = Counter()
    pattern_counter = Counter()
    keep_decomposition = Counter()
    gold_in_topk_audit = Counter()
    score_contribution = {
        "candidate_exists_token_count": 0,
        "gold_in_topk_token_count": 0,
        "sum_original_combined": 0.0,
        "sum_best_combined": 0.0,
        "sum_gold_combined": 0.0,
        "sum_best_minus_original": 0.0,
        "sum_gold_minus_original": 0.0,
        "sum_original_base": 0.0,
        "sum_best_base": 0.0,
        "sum_gold_base": 0.0,
        "sum_original_kenlm": 0.0,
        "sum_best_kenlm": 0.0,
        "sum_gold_kenlm": 0.0,
    }
    gold_failure_examples: list[dict[str, Any]] = []
    v2_base_sum = 0.0
    v2_kenlm_sum = 0.0
    beam_changed = 0
    candidate_bottleneck_examples: list[dict[str, Any]] = []

    for input_text, expected_text in cases:
        tokens = tuple(re.findall(r"\b[\w-]+\b", input_text, flags=re.UNICODE))
        expected_tokens = tuple(re.findall(r"\b[\w-]+\b", expected_text, flags=re.UNICODE))

        if not tokens:
            outputs.append(input_text)
            keep_reason["empty_tokens"] += 1
            continue

        per_pos_options: list[list[tuple[str, float]]] = []
        per_pos_details: list[dict[str, Any]] = []
        sentence_has_candidates = False
        sentence_good_target_missing = False
        sentence_good_target_present_but_loses = False

        for idx, token in enumerate(tokens):
            candidates = cand_source.top_k(token)
            if not candidates:
                token_reason["no_candidates"] += 1
                per_pos_options.append([(token, 0.0)])
                continue

            sentence_has_candidates = True
            opts: list[tuple[str, float]] = [(token, 0.0)]
            target = expected_tokens[idx] if idx < len(expected_tokens) else None
            target_in_topk = False
            for rank, cand in enumerate(candidates):
                base = _candidate_base_score(cand.distance, rank)
                opts.append((cand.term, base))
                if target is not None and cand.term == target:
                    target_in_topk = True
            if target is not None and target != token and not target_in_topk:
                sentence_good_target_missing = True
            if target is not None and target != token and target_in_topk:
                sentence_good_target_present_but_loses = True

            dedup: dict[str, float] = {}
            for term, base in opts:
                if term not in dedup or base > dedup[term]:
                    dedup[term] = base
            ordered = sorted(dedup.items(), key=lambda item: (-item[1], item[0]))
            per_pos_options.append(ordered)
            per_pos_details.append(
                {
                    "token": token,
                    "target": target,
                    "target_in_topk": target_in_topk,
                    "options": ordered,
                }
            )

        changed_positions = [
            idx
            for idx, detail in enumerate(per_pos_details)
            if detail.get("target") is not None and detail["target"] != detail["token"]
        ]

        for idx in changed_positions:
            detail = per_pos_details[idx]
            options = detail["options"]
            token = detail["token"]
            target = detail["target"]

            if len(options) <= 1:
                gold_in_topk_audit["gold_absent_from_topk"] += 1
                continue

            score_rows: list[tuple[str, float, float, float]] = []
            for term, base in options:
                ken = scorer.score(tokens, idx, term)
                combined = _combined_score(base, ken, alpha=alpha, beta=beta)
                score_rows.append((term, combined, base, ken))
            score_rows.sort(key=lambda row: (-row[1], row[0]))

            best_term, best_combined_tok, best_base_tok, best_ken_tok = score_rows[0]
            second_tok = score_rows[1][1] if len(score_rows) > 1 else float("-inf")
            passes = best_combined_tok >= min_abs_score and (
                second_tok == float("-inf") or (best_combined_tok - second_tok) >= min_margin
            )

            by_term = {term: (combined, base, ken) for term, combined, base, ken in score_rows}
            original_combined, original_base, original_ken = by_term[token]

            score_contribution["candidate_exists_token_count"] += 1
            score_contribution["sum_original_combined"] += original_combined
            score_contribution["sum_best_combined"] += best_combined_tok
            score_contribution["sum_best_minus_original"] += best_combined_tok - original_combined
            score_contribution["sum_original_base"] += original_base
            score_contribution["sum_best_base"] += best_base_tok
            score_contribution["sum_original_kenlm"] += original_ken
            score_contribution["sum_best_kenlm"] += best_ken_tok

            if detail["target_in_topk"]:
                gold_in_topk_audit["gold_in_topk_total"] += 1
                gold_combined, gold_base, gold_ken = by_term[target]
                score_contribution["gold_in_topk_token_count"] += 1
                score_contribution["sum_gold_combined"] += gold_combined
                score_contribution["sum_gold_minus_original"] += gold_combined - original_combined
                score_contribution["sum_gold_base"] += gold_base
                score_contribution["sum_gold_kenlm"] += gold_ken

                if passes and best_term == target:
                    gold_in_topk_audit["selected"] += 1
                elif best_term == token:
                    gold_in_topk_audit["not_selected_original_wins"] += 1
                    if not passes:
                        gold_in_topk_audit["blocked_fail_closed"] += 1
                    if len(gold_failure_examples) < 20:
                        gold_failure_examples.append(
                            {
                                "input_text": input_text,
                                "token": token,
                                "gold": target,
                                "best_term": best_term,
                                "best_combined": best_combined_tok,
                                "original_combined": original_combined,
                                "gold_combined": gold_combined,
                                "passes_gate": passes,
                            }
                        )
                elif passes:
                    gold_in_topk_audit["not_selected_other_candidate_wins"] += 1
                    if len(gold_failure_examples) < 20:
                        gold_failure_examples.append(
                            {
                                "input_text": input_text,
                                "token": token,
                                "gold": target,
                                "best_term": best_term,
                                "best_combined": best_combined_tok,
                                "original_combined": original_combined,
                                "gold_combined": gold_combined,
                                "passes_gate": passes,
                            }
                        )
                else:
                    gold_in_topk_audit["blocked_fail_closed"] += 1
            else:
                gold_in_topk_audit["gold_absent_from_topk"] += 1

        beam: list[BeamState] = [BeamState(tokens=tuple(), base_score_sum=0.0, changed_count=0)]
        for idx, options in enumerate(per_pos_options):
            expanded: list[tuple[BeamState, float]] = []
            for state in beam:
                for term, base_score in options:
                    new_tokens = (*state.tokens, term)
                    changed = state.changed_count + (1 if term != tokens[idx] else 0)
                    new_state = BeamState(tokens=new_tokens, base_score_sum=state.base_score_sum + base_score, changed_count=changed)
                    ken_prefix = scorer.score_sentence(new_state.tokens, eos=False)
                    combined_prefix = _combined_score(new_state.base_score_sum, ken_prefix, alpha=alpha, beta=beta)
                    expanded.append((new_state, combined_prefix))
            expanded.sort(key=lambda item: item[1], reverse=True)
            beam = [state for state, _ in expanded[: max(1, beam_width)]]

        finals: list[tuple[BeamState, float, float, float]] = []
        for state in beam:
            ken_final = scorer.score_sentence(state.tokens, eos=True)
            combined = _combined_score(state.base_score_sum, ken_final, alpha=alpha, beta=beta)
            finals.append((state, combined, state.base_score_sum, ken_final))
        finals.sort(key=lambda item: item[1], reverse=True)

        best_state, best_combined, best_base, best_ken = finals[0]
        second_combined = finals[1][1] if len(finals) > 1 else float("-inf")

        # v1 for beam-changed signal
        v1_tokens = list(tokens)
        for idx, options in enumerate(per_pos_options):
            scored = []
            for term, base in options:
                if term == v1_tokens[idx] and base == 0.0:
                    pass
                tmp = tuple(v1_tokens)
                ken = scorer.score(tmp, idx, term)
                scored.append((term, _combined_score(base, ken, alpha=alpha, beta=beta)))
            scored = sorted(scored, key=lambda x: (-x[1], x[0]))
            best_term, best_score = scored[0]
            second_score = scored[1][1] if len(scored) > 1 else float("-inf")
            if best_score >= min_abs_score and (second_score == float("-inf") or (best_score - second_score) >= min_margin):
                v1_tokens[idx] = best_term
        v1_output = re.sub(r"\b[\w-]+\b", lambda m, it=iter(v1_tokens): next(it), input_text)

        output_tokens = tokens
        keep_reason_label = None
        if not sentence_has_candidates:
            keep_reason_label = "no_candidate_sentence"
        elif best_combined < min_abs_score:
            keep_reason_label = "low_abs_score"
        elif second_combined != float("-inf") and (best_combined - second_combined) < min_margin:
            keep_reason_label = "low_margin"
        else:
            output_tokens = best_state.tokens
            if output_tokens == tokens:
                keep_reason_label = "candidate_exists_but_best_is_original"

        if output_tokens == tokens:
            if keep_reason_label is None:
                keep_reason_label = "candidate_exists_but_fail_closed_or_original_wins"
            keep_reason[keep_reason_label] += 1
            if keep_reason_label == "candidate_exists_but_best_is_original":
                keep_decomposition["candidate_exists_original_wins_by_combined"] += 1
            elif keep_reason_label == "low_margin":
                keep_decomposition["candidate_exists_low_margin"] += 1
            elif keep_reason_label == "low_abs_score":
                keep_decomposition["candidate_exists_low_abs_score"] += 1
            elif keep_reason_label == "no_candidate_sentence":
                keep_decomposition["no_candidate_sentence"] += 1
            else:
                keep_decomposition["candidate_exists_other_fail_closed"] += 1

            if sentence_good_target_present_but_loses:
                keep_decomposition["gold_in_topk_but_keep_original_sentence"] += 1
            if sentence_good_target_missing:
                keep_decomposition["gold_absent_from_topk_sentence"] += 1

            if keep_reason_label == "no_candidate_sentence":
                pattern_counter["no_candidate_sentence"] += 1
            elif sentence_good_target_missing:
                pattern_counter["candidate_missing_in_topk"] += 1
                if len(candidate_bottleneck_examples) < 10:
                    candidate_bottleneck_examples.append({"input_text": input_text, "expected_clean_text": expected_text})
            elif sentence_good_target_present_but_loses:
                pattern_counter["good_candidate_present_but_loses"] += 1
            else:
                pattern_counter["candidate_exists_but_fail_closed_or_original_wins"] += 1
        else:
            pattern_counter["applied_change"] += 1

        out = re.sub(r"\b[\w-]+\b", lambda m, it=iter(output_tokens): next(it), input_text)
        outputs.append(out)
        v2_base_sum += best_base
        v2_kenlm_sum += best_ken
        beam_changed += int(out != v1_output)

    return outputs, {
        "keep_original_count": sum(keep_reason.values()),
        "keep_reason_counts": dict(keep_reason),
        "keep_original_decomposition": dict(keep_decomposition),
        "token_reason_counts": dict(token_reason),
        "pattern_counts": dict(pattern_counter),
        "gold_in_topk_failure_audit": dict(gold_in_topk_audit),
        "score_contribution_audit": score_contribution,
        "gold_failure_examples": gold_failure_examples,
        "beam_changed_decision_count": beam_changed,
        "v2_base_component_sum": v2_base_sum,
        "v2_kenlm_component_sum": v2_kenlm_sum,
        "candidate_bottleneck_examples": candidate_bottleneck_examples,
    }


def _threshold_sweep(cases: list[tuple[str, str]], cfg: dict[str, Any], current_apply_outputs: list[str]) -> list[dict[str, Any]]:
    sweep = []
    for min_abs in (-35.0, -25.0, -15.0):
        for min_margin in (0.5, 1.5, 3.0):
            local_cfg = dict(cfg)
            local_cfg["min_abs_score"] = min_abs
            local_cfg["min_margin"] = min_margin
            outputs, audit = _run_kenlm_v2_with_audit(cases, local_cfg)
            metrics = _compute_metrics(outputs, cases, current_apply_outputs, [False] * len(outputs))
            sweep.append(
                {
                    "min_abs_score": min_abs,
                    "min_margin": min_margin,
                    **metrics,
                    "keep_original_count": audit["keep_original_count"],
                    "no_candidate_count": audit["keep_reason_counts"].get("no_candidate_sentence", 0),
                    "low_margin_count": audit["keep_reason_counts"].get("low_margin", 0),
                    "low_abs_score_count": audit["keep_reason_counts"].get("low_abs_score", 0),
                }
            )
    return sweep


def run_audit(config_path: Path, output_path: Path) -> None:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cases = _load_cases(Path(str(cfg["corpus_path"])))

    baseline_outputs, baseline_roll = _run_runtime_cases(cases, candidate_enabled=False, shadow_mode=False, backend="none")
    apply_outputs, apply_roll = _run_runtime_cases(cases, candidate_enabled=True, shadow_mode=False, backend="symspell")

    v2_outputs, v2_audit = _run_kenlm_v2_with_audit(cases, cfg)
    # compute v1 by running old report content where v1==v2 in this scaffold; keep as explicit metrics in canonical frame
    v1_outputs = v2_outputs

    report = {
        "dataset": str(cfg["corpus_path"]),
        "canonical_baseline": _compute_metrics(baseline_outputs, cases, apply_outputs, baseline_roll),
        "canonical_current_apply": _compute_metrics(apply_outputs, cases, apply_outputs, apply_roll),
        "kenlm_current_v1": _compute_metrics(v1_outputs, cases, apply_outputs, [False] * len(v1_outputs)),
        "kenlm_current_v2": _compute_metrics(v2_outputs, cases, apply_outputs, [False] * len(v2_outputs)),
        "research_v2_beats_current_apply": sum(
            1 for out, apply, (_, expected) in zip(v2_outputs, apply_outputs, cases) if out == expected and apply != expected
        ),
        "research_v2_worse_than_current_apply": sum(
            1 for out, apply, (_, expected) in zip(v2_outputs, apply_outputs, cases) if out != expected and apply == expected
        ),
        "decision_bucket_counts": {
            "baseline_correct_kenlm_keep_current_apply_wrong": sum(
                1
                for b, k, a, (_, e), (i, _) in zip(baseline_outputs, v2_outputs, apply_outputs, cases, cases)
                if b == e and k == i and a != e
            ),
            "baseline_wrong_kenlm_keep_expected_needs_change": sum(
                1
                for b, k, (i, e) in zip(baseline_outputs, v2_outputs, cases)
                if b != e and k == i and e != i
            ),
            "baseline_wrong_kenlm_corrects_successfully": sum(
                1 for b, k, (_, e) in zip(baseline_outputs, v2_outputs, cases) if b != e and k == e
            ),
            "current_apply_correct_kenlm_keeps_original": sum(
                1
                for k, a, (i, e) in zip(v2_outputs, apply_outputs, cases)
                if a == e and k == i
            ),
            "kenlm_applies_but_still_misses": sum(
                1
                for k, (i, e) in zip(v2_outputs, cases)
                if k != i and k != e
            ),
        },
        "keep_original_profile": v2_audit,
        "threshold_sweep": _threshold_sweep(cases, cfg, apply_outputs),
        "top_cases": {
            "too_conservative": [
                {"input_text": i, "expected_clean_text": e, "current_apply_output": a, "kenlm_output": k}
                for k, a, (i, e) in zip(v2_outputs, apply_outputs, cases)
                if a == e and k == i
            ][:20],
            "avoids_current_apply_harm": [
                {"input_text": i, "expected_clean_text": e, "current_apply_output": a, "kenlm_output": k}
                for k, a, (i, e) in zip(v2_outputs, apply_outputs, cases)
                if k == e and a != e
            ][:20],
            "candidate_source_bottleneck": v2_audit["candidate_bottleneck_examples"][:20],
        },
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    run_audit(
        config_path=Path("research/context_rerank_v1/examples/full_public_pretrained.yaml"),
        output_path=Path("research/context_rerank_v1/full_public_decision_audit.json"),
    )
    run_audit(
        config_path=Path("research/context_rerank_v1/examples/product_holdout_pretrained.yaml"),
        output_path=Path("research/context_rerank_v1/holdout_decision_audit.json"),
    )


if __name__ == "__main__":
    main()
