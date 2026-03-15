from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator

from .candidate_source import Candidate, LargeLexiconCandidateSource
from .decision import fail_closed_pick
from .report import build_report
from .scorers import KenLMScorer, SentenceCandidateScorer

TOKEN_RE = re.compile(r"\b[\w-]+\b", flags=re.UNICODE)


@dataclass(frozen=True)
class ReplayCase:
    input_text: str
    expected_clean_text: str


@dataclass(frozen=True)
class CurrentApplyResult:
    output: str
    rollback_related: bool


@dataclass(frozen=True)
class BeamState:
    tokens: tuple[str, ...]
    base_score_sum: float
    changed_count: int


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid config format")
    return payload


def load_cases(path: Path) -> tuple[ReplayCase, ...]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        return _load_cases_yaml(path)
    return _load_cases_jsonl(path)


def _load_cases_jsonl(path: Path) -> tuple[ReplayCase, ...]:
    rows: list[ReplayCase] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid record at line {i}")
        input_text = payload.get("input_text") or payload.get("input")
        expected = payload.get("expected_clean_text")
        if not isinstance(input_text, str) or not isinstance(expected, str):
            raise ValueError(f"invalid schema at line {i}")
        rows.append(ReplayCase(input_text=input_text, expected_clean_text=expected))
    return tuple(rows)


def _load_cases_yaml(path: Path) -> tuple[ReplayCase, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid yaml corpus schema")
    smart_rows = payload.get("smart")
    if not isinstance(smart_rows, list):
        raise ValueError("invalid yaml corpus schema: smart list missing")

    rows: list[ReplayCase] = []
    for i, row in enumerate(smart_rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"invalid yaml row at index {i}")
        input_text = row.get("input")
        expected = row.get("expected_clean_text")
        if not isinstance(input_text, str) or not isinstance(expected, str):
            raise ValueError(f"invalid yaml row schema at index {i}")
        rows.append(ReplayCase(input_text=input_text, expected_clean_text=expected))
    return tuple(rows)


def _load_external_lm_corpus(path: Path) -> tuple[str, ...]:
    texts = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not texts:
        raise ValueError(f"external lm corpus is empty: {path}")
    return tuple(texts)


def _resolve_model_path(model_path_or_url: str) -> Path:
    parsed = urlparse(model_path_or_url)
    if parsed.scheme in {"http", "https"}:
        cache_root = Path(tempfile.gettempdir()) / "gramlynx_context_rerank_v1_models"
        cache_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(model_path_or_url.encode("utf-8")).hexdigest()[:16]
        suffix = Path(parsed.path).suffix or ".arpa"
        local_path = cache_root / f"external_{digest}{suffix}"
        if not local_path.exists():
            req = Request(model_path_or_url, headers={"User-Agent": "GramLynx-research/1.0"})
            with urlopen(req, timeout=120) as response:
                local_path.write_bytes(response.read())
        return local_path

    return Path(model_path_or_url)


def make_scorer(config: dict[str, Any]) -> SentenceCandidateScorer:
    scorer_type = str(config["scorer_type"])
    if scorer_type != "kenlm":
        raise ValueError(f"unsupported scorer_type: {scorer_type}")

    model_path_raw = config.get("kenlm_model_path")
    if model_path_raw:
        resolved_path = _resolve_model_path(str(model_path_raw))
        return KenLMScorer(model_path=resolved_path)

    lm_corpus_path_raw = config.get("kenlm_training_corpus_path")
    if not lm_corpus_path_raw:
        raise ValueError(
            "leakage-safe mode requires independent scorer source: set kenlm_model_path or kenlm_training_corpus_path"
        )

    lm_corpus_path = Path(str(lm_corpus_path_raw))
    lm_texts = _load_external_lm_corpus(lm_corpus_path)
    temp_path = Path(tempfile.gettempdir()) / "gramlynx_context_rerank_v1_external_lm.arpa"
    trained_path = KenLMScorer.train_bigram_arpa(corpus_texts=lm_texts, output_path=temp_path)
    return KenLMScorer(model_path=trained_path)


def _candidate_base_score(candidate: Candidate, rank: int) -> float:
    return -(1.0 * float(candidate.distance) + 0.15 * float(rank))


def _combined_score(base_component: float, kenlm_component: float, alpha: float, beta: float) -> float:
    return alpha * base_component + beta * kenlm_component


def run_replay(config: dict[str, Any], cases: tuple[ReplayCase, ...]) -> dict[str, Any]:
    extra_dictionary_sources = tuple(str(p) for p in config.get("extra_dictionary_sources", []))
    candidate_source = LargeLexiconCandidateSource(
        dictionary_path=str(config["dictionary_source"]),
        top_k=int(config["top_k"]),
        max_edit_distance=int(config.get("max_edit_distance", 3)),
        extra_dictionary_paths=extra_dictionary_sources,
    )
    scorer = make_scorer(config)
    if not isinstance(scorer, KenLMScorer):
        raise TypeError("kenlm_v2 requires KenLMScorer")

    current_apply = _run_current_apply(cases)
    alpha = float(config.get("combined_alpha", 1.0))
    beta = float(config.get("combined_beta", 1.0))
    beam_width = int(config.get("beam_width", 4))

    outputs: list[dict[str, Any]] = []
    for case in cases:
        apply_result = current_apply[case.input_text]
        v1_output = _apply_research_replay_v1(
            text=case.input_text,
            candidate_source=candidate_source,
            scorer=scorer,
            min_margin=float(config["min_margin"]),
            min_abs_score=float(config["min_abs_score"]),
            alpha=alpha,
            beta=beta,
        )
        v2_result = _apply_research_replay_v2(
            text=case.input_text,
            candidate_source=candidate_source,
            scorer=scorer,
            min_margin=float(config["min_margin"]),
            min_abs_score=float(config["min_abs_score"]),
            alpha=alpha,
            beta=beta,
            beam_width=beam_width,
        )
        outputs.append(
            {
                "input_text": case.input_text,
                "expected_clean_text": case.expected_clean_text,
                "baseline_output": case.input_text,
                "current_apply_output": apply_result.output,
                "research_replay_v1_output": v1_output,
                "research_replay_v2_output": v2_result["output_text"],
                "current_apply_rollback_related": apply_result.rollback_related,
                "research_replay_v1_rollback_related": False,
                "research_replay_v2_rollback_related": False,
                "v2_base_component": v2_result["base_component"],
                "v2_kenlm_component": v2_result["kenlm_component"],
                "beam_changed_decision": v2_result["output_text"] != v1_output,
            }
        )

    return build_report(outputs)


def _run_current_apply(cases: tuple[ReplayCase, ...]) -> dict[str, CurrentApplyResult]:
    prev_cfg = os.environ.get("GRAMLYNX_CONFIG_YAML")
    reset_app_config_cache()
    results: dict[str, CurrentApplyResult] = {}
    try:
        for i, case in enumerate(cases, start=1):
            orchestrator = Orchestrator(correlation_id=f"research-rerank-v1-{i}")
            with contextlib.redirect_stdout(io.StringIO()):
                output = orchestrator.clean(case.input_text, mode="smart")
            stats = orchestrator.last_run_stats
            results[case.input_text] = CurrentApplyResult(
                output=output,
                rollback_related=bool(stats.get("rollback_applied", False)),
            )
    finally:
        if prev_cfg is None:
            os.environ.pop("GRAMLYNX_CONFIG_YAML", None)
        else:
            os.environ["GRAMLYNX_CONFIG_YAML"] = prev_cfg
        reset_app_config_cache()
    return results


def _apply_research_replay_v1(
    text: str,
    candidate_source: LargeLexiconCandidateSource,
    scorer: KenLMScorer,
    min_margin: float,
    min_abs_score: float,
    alpha: float,
    beta: float,
) -> str:
    tokens = TOKEN_RE.findall(text)
    if not tokens:
        return text

    updated = list(tokens)
    for idx, token in enumerate(tokens):
        candidates = candidate_source.top_k(token)
        if not candidates:
            continue

        scored: list[tuple[str, float]] = []
        for rank, cand in enumerate(candidates):
            base = _candidate_base_score(cand, rank)
            tmp_tokens = tuple(updated)
            ken = scorer.score(tmp_tokens, idx, cand.term)
            scored.append((cand.term, _combined_score(base, ken, alpha=alpha, beta=beta)))

        decision = fail_closed_pick(
            original_token=updated[idx],
            scored_candidates=tuple(scored),
            min_margin=min_margin,
            min_abs_score=min_abs_score,
        )
        updated[idx] = decision.output_token

    iterator = iter(updated)
    return TOKEN_RE.sub(lambda _: next(iterator), text)


def _apply_research_replay_v2(
    text: str,
    candidate_source: LargeLexiconCandidateSource,
    scorer: KenLMScorer,
    min_margin: float,
    min_abs_score: float,
    alpha: float,
    beta: float,
    beam_width: int,
) -> dict[str, Any]:
    original_tokens = tuple(TOKEN_RE.findall(text))
    if not original_tokens:
        return {"output_text": text, "base_component": 0.0, "kenlm_component": 0.0}

    per_pos_options: list[list[tuple[str, float]]] = []
    for token in original_tokens:
        opts: list[tuple[str, float]] = [(token, 0.0)]
        candidates = candidate_source.top_k(token)
        for rank, cand in enumerate(candidates):
            opts.append((cand.term, _candidate_base_score(cand, rank)))
        dedup: dict[str, float] = {}
        for term, base in opts:
            if term not in dedup or base > dedup[term]:
                dedup[term] = base
        ordered = sorted(dedup.items(), key=lambda item: (-item[1], item[0]))
        per_pos_options.append(ordered)

    beam: list[BeamState] = [BeamState(tokens=tuple(), base_score_sum=0.0, changed_count=0)]
    for idx, options in enumerate(per_pos_options):
        expanded: list[tuple[BeamState, float]] = []
        for state in beam:
            for term, base_score in options:
                new_tokens = (*state.tokens, term)
                changed = state.changed_count + (1 if term != original_tokens[idx] else 0)
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

    output_tokens = original_tokens
    if best_combined >= min_abs_score and (second_combined == float("-inf") or (best_combined - second_combined) >= min_margin):
        output_tokens = best_state.tokens

    iterator = iter(output_tokens)
    output_text = TOKEN_RE.sub(lambda _: next(iterator), text)
    return {
        "output_text": output_text,
        "base_component": best_base,
        "kenlm_component": best_ken,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline context rerank replay scaffold")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    cases = load_cases(Path(str(config["corpus_path"])))
    result = run_replay(config, cases)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
