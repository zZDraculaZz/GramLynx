"""Offline KenLM-style candidate rerank scaffold (research-only, non-production).

This module intentionally does not modify runtime/API/config defaults.
It provides an offline replay path with a sentence-scoring hook that can be
backed by a real KenLM scorer in a future step.
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
from typing import Protocol

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator
from app.core.protected_zones.detector import mask_protected_zones, restore_protected_zones
from app.core.stages.helpers import deterministic_spelling as ds

DEFAULT_FULL_PUBLIC = Path("tests/cases/ruspellgold_full_public.jsonl")
DEFAULT_SUBSET = Path("tests/cases/ruspellgold_benchmark.jsonl")
DEFAULT_PRODUCT_HOLDOUT = Path("tests/cases/product_regression_user_texts.yml")
DEFAULT_DICTIONARY = "app/resources/ru_dictionary_v7.txt"
DEFAULT_OUTPUT_JSON = Path("offline_kenlm_rerank_experiment_report.json")
DEFAULT_OUTPUT_MD = Path("offline_kenlm_rerank_experiment_report.md")

TOKEN_PATTERN = re.compile(r"\b[\w-]{2,}\b", flags=re.UNICODE)


@dataclass(frozen=True)
class Case:
    input_text: str
    expected_clean_text: str


@dataclass(frozen=True)
class Candidate:
    term: str
    dist: int
    base_rank: int
    count: int


class SentenceScorer(Protocol):
    """Sentence-level score hook for reranking.

    Real KenLM backend can implement this protocol in a follow-up step.
    Higher score means better sentence.
    """

    name: str

    def score(self, text: str) -> float:
        ...


class DeterministicPlaceholderLMScorer:
    """Deterministic placeholder scorer (offline scaffold only).

    This is NOT a language model. It only keeps the pipeline deterministic and
    allows wiring replay/report flow before plugging a real LM scorer.
    """

    name = "deterministic_placeholder_lm"

    def score(self, text: str) -> float:
        tokens = TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return -999.0
        unique_ratio = len(set(tokens)) / len(tokens)
        hyphen_bonus = sum(1 for tok in tokens if "-" in tok) * 0.01
        length_penalty = sum(1 for tok in tokens if len(tok) == 1) * 0.05
        digit_penalty = sum(1 for tok in tokens if any(ch.isdigit() for ch in tok)) * 0.03
        return round(unique_ratio + hyphen_bonus - length_penalty - digit_penalty, 6)


def _load_jsonl_cases(path: Path) -> tuple[Case, ...]:
    rows: list[Case] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid row type at line {idx}")
        inp = payload.get("input_text")
        exp = payload.get("expected_clean_text")
        if not isinstance(inp, str) or not isinstance(exp, str) or not inp:
            raise ValueError(f"invalid schema at line {idx}")
        rows.append(Case(input_text=inp, expected_clean_text=exp))
    if not rows:
        raise ValueError(f"empty dataset: {path}")
    return tuple(rows)


def _load_product_holdout_cases(path: Path) -> tuple[Case, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid holdout structure")
    smart = payload.get("smart")
    if not isinstance(smart, list):
        raise ValueError("invalid holdout smart section")
    rows: list[Case] = []
    for idx, item in enumerate(smart, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"invalid holdout row type at index {idx}")
        inp = item.get("input")
        exp = item.get("expected_clean_text")
        if not isinstance(inp, str) or not isinstance(exp, str) or not inp:
            raise ValueError(f"invalid holdout schema at index {idx}")
        rows.append(Case(input_text=inp, expected_clean_text=exp))
    if not rows:
        raise ValueError("empty holdout dataset")
    return tuple(rows)


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


def _run_standard_mode(mode_label: str, cases: tuple[Case, ...], dictionary_source: str) -> list[str]:
    if mode_label == "baseline":
        candidate_enabled, shadow_mode, backend = False, False, "none"
    elif mode_label == "symspell_apply":
        candidate_enabled, shadow_mode, backend = True, False, "symspell"
    else:
        raise ValueError(mode_label)

    if backend == "symspell" and importlib.util.find_spec("symspellpy") is None:
        raise RuntimeError("candidate backend unavailable: symspellpy is not installed")

    cfg_path = Path(tempfile.gettempdir()) / f"gramlynx_kenlm_research_{mode_label}.yml"
    cfg_path.write_text(
        _runtime_config(candidate_enabled, shadow_mode, backend, dictionary_source),
        encoding="utf-8",
    )

    prev = os.environ.get("GRAMLYNX_CONFIG_YAML")
    os.environ["GRAMLYNX_CONFIG_YAML"] = str(cfg_path)
    reset_app_config_cache()

    out: list[str] = []
    try:
        for index, case in enumerate(cases, start=1):
            orchestrator = Orchestrator(correlation_id=f"kenlm-rerank-{mode_label}-{index}")
            with contextlib.redirect_stdout(io.StringIO()):
                out.append(orchestrator.clean(case.input_text, mode="smart"))
    finally:
        if prev is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev
        reset_app_config_cache()
    return out


def _topk_candidates(token: str, dictionary_source: str, max_k: int = 3, max_edit_distance: int = 1) -> tuple[Candidate, ...]:
    try:
        from symspellpy import Verbosity
    except Exception:
        return ()

    symspell = ds._get_symspell(dictionary_source)
    if symspell is None:
        return ()

    suggestions = symspell.lookup(
        token,
        Verbosity.CLOSEST,
        max_edit_distance=max_edit_distance,
        include_unknown=False,
        transfer_casing=False,
    )
    top: list[Candidate] = []
    for idx, suggestion in enumerate(suggestions):
        term = suggestion.term
        dist = int(suggestion.distance)
        if term == token or dist > max_edit_distance:
            continue
        if not ds._safe_candidate_token(term):
            continue
        top.append(Candidate(term=term, dist=dist, base_rank=idx, count=int(suggestion.count)))

    top.sort(key=lambda row: (row.dist, row.base_rank, -row.count, row.term))
    return tuple(top[: max(1, max_k)])


def _build_variant(tokens: list[str], index: int, repl: str) -> str:
    patched = list(tokens)
    patched[index] = repl
    return " ".join(patched)


def _offline_rerank_apply(text: str, scorer: SentenceScorer, dictionary_source: str, min_margin: float = 0.05) -> tuple[str, int]:
    """Fail-closed offline replay over baseline text.

    Returns (text, applied_edits). If candidate source or scorer hook cannot provide
    a safe winner, the token remains unchanged.
    """

    masked, placeholders, _ = mask_protected_zones(text)
    tokens = TOKEN_PATTERN.findall(masked)
    if not tokens:
        return text, 0

    applied = 0
    for idx, token in enumerate(tokens):
        if not ds._safe_ru_token(token):
            continue
        candidates = _topk_candidates(token=token, dictionary_source=dictionary_source)
        if not candidates:
            continue

        base_variant = " ".join(tokens)
        base_score = scorer.score(base_variant)

        best_term = token
        best_score = base_score
        for cand in candidates:
            cand_score = scorer.score(_build_variant(tokens, idx, cand.term))
            if cand_score > best_score:
                best_term = cand.term
                best_score = cand_score

        if best_term == token:
            continue
        if (best_score - base_score) < min_margin:
            continue
        if ds._is_plural_to_singular_drop(token, best_term):
            continue

        tokens[idx] = best_term
        applied += 1

    restored = restore_protected_zones(" ".join(tokens), placeholders)
    return restored, applied


def _summarize(cases: tuple[Case, ...], outputs: list[str]) -> dict[str, int | float]:
    total = len(cases)
    exact = sum(1 for case, out in zip(cases, outputs) if case.expected_clean_text == out)
    wrong_change = sum(1 for case, out in zip(cases, outputs) if out != case.expected_clean_text and out != case.input_text)
    unchanged_when_expected_change = sum(
        1 for case, out in zip(cases, outputs) if case.input_text != case.expected_clean_text and out == case.input_text
    )
    return {
        "total_cases": total,
        "exact_match_pass_count": exact,
        "exact_match_pass_rate": round((exact / total) if total else 0.0, 6),
        "wrong_change": wrong_change,
        "unchanged_when_expected_change": unchanged_when_expected_change,
    }


def run_dataset_experiment(cases: tuple[Case, ...], dictionary_source: str, scorer: SentenceScorer) -> dict[str, object]:
    baseline_out = _run_standard_mode("baseline", cases, dictionary_source=dictionary_source)
    apply_out = _run_standard_mode("symspell_apply", cases, dictionary_source=dictionary_source)

    rerank_out: list[str] = []
    total_applied = 0
    for text in baseline_out:
        replay_text, applied = _offline_rerank_apply(text, scorer=scorer, dictionary_source=dictionary_source)
        rerank_out.append(replay_text)
        total_applied += applied

    return {
        "candidate_source": "symspell_topk",
        "top_k": 3,
        "sentence_scorer": scorer.name,
        "fail_closed_fallback": "no_apply",
        "comparison_targets": ["baseline", "current_apply", "offline_rerank"],
        "baseline": _summarize(cases, baseline_out),
        "current_apply": _summarize(cases, apply_out),
        "offline_rerank": {
            **_summarize(cases, rerank_out),
            "rerank_applied_edits": total_applied,
        },
    }


def run_experiment(
    full_public_path: Path = DEFAULT_FULL_PUBLIC,
    subset_path: Path = DEFAULT_SUBSET,
    product_holdout_path: Path = DEFAULT_PRODUCT_HOLDOUT,
    dictionary_source: str = DEFAULT_DICTIONARY,
) -> dict[str, object]:
    scorer = DeterministicPlaceholderLMScorer()
    full_public_cases = _load_jsonl_cases(full_public_path)
    subset_cases = _load_jsonl_cases(subset_path)
    product_holdout_cases = _load_product_holdout_cases(product_holdout_path)

    return {
        "research_track": "offline_kenlm_style_rerank_scaffold",
        "production_integration": "none",
        "datasets": {
            "full_public_ruspellgold": run_dataset_experiment(full_public_cases, dictionary_source=dictionary_source, scorer=scorer),
            "subset_benchmark": run_dataset_experiment(subset_cases, dictionary_source=dictionary_source, scorer=scorer),
            "product_regression_holdout": run_dataset_experiment(
                product_holdout_cases,
                dictionary_source=dictionary_source,
                scorer=scorer,
            ),
        },
    }


def _render_md(report: dict[str, object]) -> str:
    datasets = report["datasets"]
    lines = [
        "# Offline KenLM-style Rerank Experiment Scaffold",
        "",
        "_Research-only offline track. Not a production path._",
        "",
    ]
    for dataset_name, payload in datasets.items():
        assert isinstance(payload, dict)
        lines.append(f"## {dataset_name}")
        lines.append("")
        lines.append(f"- candidate_source: `{payload['candidate_source']}`")
        lines.append(f"- top_k: `{payload['top_k']}`")
        lines.append(f"- sentence_scorer: `{payload['sentence_scorer']}`")
        lines.append(f"- fail_closed_fallback: `{payload['fail_closed_fallback']}`")
        lines.append(f"- comparison_targets: `{', '.join(payload['comparison_targets'])}`")
        lines.append("")
        lines.append("| target | exact_match | wrong_change | unchanged_when_expected_change |")
        lines.append("|---|---:|---:|---:|")
        for target in ("baseline", "current_apply", "offline_rerank"):
            stats = payload[target]
            lines.append(
                f"| {target} | {stats['exact_match_pass_count']} / {stats['exact_match_pass_rate']:.6f} "
                f"| {stats['wrong_change']} | {stats['unchanged_when_expected_change']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline KenLM-style rerank experiment scaffold")
    parser.add_argument("--full-public", type=Path, default=DEFAULT_FULL_PUBLIC)
    parser.add_argument("--subset", type=Path, default=DEFAULT_SUBSET)
    parser.add_argument("--product-holdout", type=Path, default=DEFAULT_PRODUCT_HOLDOUT)
    parser.add_argument("--dictionary", default=DEFAULT_DICTIONARY)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    report = run_experiment(
        full_public_path=args.full_public,
        subset_path=args.subset,
        product_holdout_path=args.product_holdout,
        dictionary_source=args.dictionary,
    )

    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(_render_md(report), encoding="utf-8")


if __name__ == "__main__":
    main()
