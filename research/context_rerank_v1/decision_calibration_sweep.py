from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from research.context_rerank_v1.audit_decision_profile import _compute_metrics, _load_cases, _run_runtime_cases
from research.context_rerank_v1.candidate_source import LargeLexiconCandidateSource
from research.context_rerank_v1.replay import BeamState, _combined_score, make_scorer
from research.context_rerank_v1.scorers.kenlm import KenLMScorer

TOKEN_RE = re.compile(r"\b[\w-]+\b", flags=re.UNICODE)


@dataclass(frozen=True)
class CalibrationVariant:
    name: str
    base_scale: float = 1.0
    original_bias: float = 0.0
    alpha: float = 1.0
    beta: float = 1.0


def _score_option(base: float, ken: float, *, variant: CalibrationVariant, is_original: bool) -> float:
    adjusted_base = variant.base_scale * base + (variant.original_bias if is_original else 0.0)
    return _combined_score(adjusted_base, ken, alpha=variant.alpha, beta=variant.beta)


def _apply_variant(
    cases: list[tuple[str, str]],
    cfg: dict[str, Any],
    variant: CalibrationVariant,
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

    min_margin = float(cfg["min_margin"])
    min_abs_score = float(cfg["min_abs_score"])
    beam_width = int(cfg.get("beam_width", 4))

    outputs: list[str] = []
    keep_reason_counts: dict[str, int] = {"no_candidate": 0, "low_abs_score": 0, "low_margin": 0, "original_wins": 0}

    token_audit: dict[tuple[int, int], str] = {}
    token_wrong_wins = 0
    gold_in_topk_total = 0
    gold_in_topk_selected = 0
    original_wins = 0
    blocked_fail_closed = 0

    for case_idx, (input_text, expected_text) in enumerate(cases):
        tokens = tuple(TOKEN_RE.findall(input_text))
        expected_tokens = tuple(TOKEN_RE.findall(expected_text))

        if not tokens:
            outputs.append(input_text)
            keep_reason_counts["no_candidate"] += 1
            continue

        per_pos_options: list[list[tuple[str, float]]] = []
        has_any_candidates = False

        for idx, token in enumerate(tokens):
            candidates = cand_source.top_k(token)
            if not candidates:
                per_pos_options.append([(token, 0.0)])
                continue
            has_any_candidates = True
            opts = [(token, 0.0)]
            for rank, cand in enumerate(candidates):
                base = -(1.0 * float(cand.distance) + 0.15 * float(rank))
                opts.append((cand.term, base))
            dedup: dict[str, float] = {}
            for term, base in opts:
                if term not in dedup or base > dedup[term]:
                    dedup[term] = base
            per_pos_options.append(sorted(dedup.items(), key=lambda x: (-x[1], x[0])))

            # token-level gold-in-top-k diagnostics on changed positions
            target = expected_tokens[idx] if idx < len(expected_tokens) else None
            if target is None or target == token:
                continue

            rows: list[tuple[str, float]] = []
            gold_seen = False
            for term, base in per_pos_options[-1]:
                if term == target:
                    gold_seen = True
                ken = scorer.score(tokens, idx, term)
                score = _score_option(base, ken, variant=variant, is_original=(term == token))
                rows.append((term, score))

            if not gold_seen:
                token_audit[(case_idx, idx)] = "gold_absent"
                continue

            gold_in_topk_total += 1
            rows.sort(key=lambda x: (-x[1], x[0]))
            best_term, best_score = rows[0]
            second_score = rows[1][1] if len(rows) > 1 else float("-inf")
            passes = best_score >= min_abs_score and (
                second_score == float("-inf") or (best_score - second_score) >= min_margin
            )
            if passes and best_term == target:
                token_audit[(case_idx, idx)] = "selected"
                gold_in_topk_selected += 1
            elif best_term == token:
                token_audit[(case_idx, idx)] = "original_wins"
                original_wins += 1
                if not passes:
                    blocked_fail_closed += 1
            elif passes:
                token_audit[(case_idx, idx)] = "wrong_candidate_wins"
                token_wrong_wins += 1
            else:
                token_audit[(case_idx, idx)] = "blocked_fail_closed"
                blocked_fail_closed += 1

        beam: list[BeamState] = [BeamState(tokens=tuple(), base_score_sum=0.0, changed_count=0)]
        for idx, options in enumerate(per_pos_options):
            expanded: list[tuple[BeamState, float]] = []
            for state in beam:
                for term, base in options:
                    new_state = BeamState(
                        tokens=(*state.tokens, term),
                        base_score_sum=state.base_score_sum + base,
                        changed_count=state.changed_count + (1 if term != tokens[idx] else 0),
                    )
                    ken_prefix = scorer.score_sentence(new_state.tokens, eos=False)
                    combined_prefix = _score_option(
                        new_state.base_score_sum,
                        ken_prefix,
                        variant=variant,
                        is_original=(new_state.tokens == tokens[: len(new_state.tokens)]),
                    )
                    expanded.append((new_state, combined_prefix))
            expanded.sort(key=lambda x: x[1], reverse=True)
            beam = [state for state, _ in expanded[: max(1, beam_width)]]

        finals: list[tuple[BeamState, float]] = []
        for state in beam:
            ken_final = scorer.score_sentence(state.tokens, eos=True)
            combined = _score_option(
                state.base_score_sum,
                ken_final,
                variant=variant,
                is_original=(state.tokens == tokens),
            )
            finals.append((state, combined))
        finals.sort(key=lambda x: x[1], reverse=True)

        best_state, best_combined = finals[0]
        second_combined = finals[1][1] if len(finals) > 1 else float("-inf")

        output_tokens = tokens
        if not has_any_candidates:
            keep_reason_counts["no_candidate"] += 1
        elif best_combined < min_abs_score:
            keep_reason_counts["low_abs_score"] += 1
        elif second_combined != float("-inf") and (best_combined - second_combined) < min_margin:
            keep_reason_counts["low_margin"] += 1
        else:
            output_tokens = best_state.tokens
            if output_tokens == tokens:
                keep_reason_counts["original_wins"] += 1

        out = re.sub(r"\b[\w-]+\b", lambda m, it=iter(output_tokens): next(it), input_text)
        outputs.append(out)

    keep_original_count = sum(1 for out, (inp, _) in zip(outputs, cases) if out == inp)
    wrong_change = sum(1 for out, (inp, exp) in zip(outputs, cases) if out != inp and out != exp)

    return outputs, {
        "keep_original_count": keep_original_count,
        "keep_reason_counts": keep_reason_counts,
        "gold_in_topk_total": gold_in_topk_total,
        "gold_in_topk_selected": gold_in_topk_selected,
        "original_wins": original_wins,
        "blocked_fail_closed": blocked_fail_closed,
        "wrong_candidate_wins": token_wrong_wins,
        "token_audit": {f"{k[0]}:{k[1]}": v for k, v in token_audit.items()},
        "wrong_change": wrong_change,
    }


def _variant_report(
    cfg_path: Path,
    variants: list[CalibrationVariant],
) -> dict[str, Any]:
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cases = _load_cases(Path(str(cfg["corpus_path"])))
    _, apply_roll = _run_runtime_cases(cases, candidate_enabled=True, shadow_mode=False, backend="symspell")
    apply_outputs, _ = _run_runtime_cases(cases, candidate_enabled=True, shadow_mode=False, backend="symspell")

    outputs_by_name: dict[str, list[str]] = {}
    audits: dict[str, dict[str, Any]] = {}

    for variant in variants:
        outs, audit = _apply_variant(cases, cfg, variant)
        outputs_by_name[variant.name] = outs
        audits[variant.name] = audit

    baseline_name = variants[0].name
    baseline_audit = audits[baseline_name]
    baseline_tokens = baseline_audit["token_audit"]

    variant_rows: list[dict[str, Any]] = []
    for variant in variants:
        name = variant.name
        outs = outputs_by_name[name]
        audit = audits[name]
        metrics = _compute_metrics(outs, cases, apply_outputs, apply_roll)

        converted_gold = sum(
            1
            for key, status in baseline_tokens.items()
            if status == "original_wins" and audit["token_audit"].get(key) == "selected"
        )
        baseline_outs = outputs_by_name[baseline_name]
        introduced_harm = sum(
            1
            for (inp, exp), out_base, out_cur in zip(cases, baseline_outs, outs)
            if out_base in {inp, exp} and out_cur != inp and out_cur != exp
        )

        original_wins_before = sum(1 for v in baseline_tokens.values() if v == "original_wins")
        original_wins_after = sum(1 for v in audit["token_audit"].values() if v == "original_wins")
        blocked_before = baseline_audit["blocked_fail_closed"]
        blocked_after = audit["blocked_fail_closed"]

        variant_rows.append(
            {
                "name": name,
                "params": {
                    "base_scale": variant.base_scale,
                    "original_bias": variant.original_bias,
                    "alpha": variant.alpha,
                    "beta": variant.beta,
                },
                **metrics,
                "keep_original_count": audit["keep_original_count"],
                "gold_in_topk_selected_count": audit["gold_in_topk_selected"],
                "gold_in_topk_total": audit["gold_in_topk_total"],
                "original_wins_before": original_wins_before,
                "original_wins_after": original_wins_after,
                "blocked_fail_closed_before": blocked_before,
                "blocked_fail_closed_after": blocked_after,
                "converted_gold_keep_to_selected": converted_gold,
                "introduced_harmful_wrong_change": introduced_harm,
                "wrong_candidate_wins": audit["wrong_candidate_wins"],
                "keep_reason_counts": audit["keep_reason_counts"],
            }
        )

    return {
        "dataset": str(cfg["corpus_path"]),
        "variants": variant_rows,
    }


def main() -> None:
    variants = [
        CalibrationVariant(name="baseline", base_scale=1.0, original_bias=0.0, alpha=1.0, beta=1.0),
        CalibrationVariant(name="base_penalty_relaxed", base_scale=0.7, original_bias=0.0, alpha=1.0, beta=1.0),
        CalibrationVariant(name="anti_original_bias", base_scale=1.0, original_bias=-0.7, alpha=1.0, beta=1.0),
        CalibrationVariant(name="kenlm_upweight", base_scale=1.0, original_bias=0.0, alpha=0.7, beta=1.3),
    ]

    full = _variant_report(Path("research/context_rerank_v1/examples/full_public_pretrained.yaml"), variants)
    holdout = _variant_report(Path("research/context_rerank_v1/examples/product_holdout_pretrained.yaml"), variants)

    Path("research/context_rerank_v1/full_public_decision_calibration_sweep.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path("research/context_rerank_v1/holdout_decision_calibration_sweep.json").write_text(
        json.dumps(holdout, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
