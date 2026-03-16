from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .candidate_source import LargeLexiconCandidateSource
from .replay import TOKEN_RE, _run_current_apply, load_cases

NON_CYRILLIC_MIX_RE = re.compile(r"(?=.*[A-Za-z])(?=.*[А-Яа-яЁё])")
HASHTAG_MENTION_RE = re.compile(r"(?:^|\s)([#@][\w-]+)")
URL_RE = re.compile(r"https?://|www\.")
REPEATED_PUNCT_RE = re.compile(r"([!?.,;:])\1+")
MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r"[,.!?;:](\S)")
WRAPPER_CHARS = set("*_`~|<>{}[]()")
QUOTE_BRACKET = set("\"'«»()[]{}")


@dataclass(frozen=True)
class TokenRow:
    token: str
    start: int
    end: int


def _token_rows(text: str) -> list[TokenRow]:
    return [TokenRow(token=m.group(0), start=m.start(), end=m.end()) for m in TOKEN_RE.finditer(text)]


def _norm(token: str) -> str:
    return token.strip().lower().replace("ё", "е")


def _shape_allowed(token: str) -> bool:
    return bool(re.fullmatch(r"[а-яе-]+", _norm(token)))


def _local_noise_flags(text: str, row: TokenRow) -> dict[str, bool]:
    prev_ch = text[row.start - 1] if row.start > 0 else ""
    next_ch = text[row.end] if row.end < len(text) else ""
    tok = row.token
    return {
        "punctuation_adjacency": bool((prev_ch and not prev_ch.isalnum() and not prev_ch.isspace()) or (next_ch and not next_ch.isalnum() and not next_ch.isspace())),
        "quote_bracket_adjacency": prev_ch in QUOTE_BRACKET or next_ch in QUOTE_BRACKET,
        "wrapper_no_touch_style": any(ch in WRAPPER_CHARS for ch in (prev_ch + next_ch)) or tok.startswith(("`", "*", "_")) or tok.endswith(("`", "*", "_")),
        "mixed_alnum_non_ru_shape": any(ch.isdigit() for ch in tok) or bool(NON_CYRILLIC_MIX_RE.search(tok)),
    }


def _case_noise_flags(text: str) -> dict[str, bool]:
    return {
        "repeated_punctuation": bool(REPEATED_PUNCT_RE.search(text)),
        "missing_extra_spaces": ("  " in text) or bool(MISSING_SPACE_AFTER_PUNCT_RE.search(text)),
        "newline_line_break_noise": "\n" in text,
        "hashtags_mentions_urls": bool(HASHTAG_MENTION_RE.search(text) or URL_RE.search(text)),
    }


def _analyze_dataset(corpus_path: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    cases = load_cases(corpus_path)
    current_apply = _run_current_apply(cases)
    source = LargeLexiconCandidateSource(
        dictionary_path=str(cfg["dictionary_source"]),
        top_k=int(cfg.get("top_k", 5)),
        max_edit_distance=int(cfg.get("max_edit_distance", 3)),
        extra_dictionary_paths=tuple(str(p) for p in cfg.get("extra_dictionary_sources", [])),
    )

    slices = Counter()
    noise_counts = Counter()
    noise_break = defaultdict(Counter)
    normalization = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals = Counter()

    for case_idx, case in enumerate(cases):
        if case.input_text == case.expected_clean_text:
            continue
        totals["expected_change_cases"] += 1

        input_rows = _token_rows(case.input_text)
        gold_rows = _token_rows(case.expected_clean_text)
        apply_rows = _token_rows(current_apply[case.input_text].output)
        case_noise = _case_noise_flags(case.input_text)

        if len(input_rows) != len(gold_rows):
            slices["segmentation_tokenization_mismatch"] += 1
            if len(examples["segmentation_tokenization_mismatch"]) < 5:
                examples["segmentation_tokenization_mismatch"].append({
                    "input": case.input_text,
                    "expected": case.expected_clean_text,
                    "current_apply": current_apply[case.input_text].output,
                })
            continue

        for idx, (inp, gold) in enumerate(zip(input_rows, gold_rows)):
            if inp.token == gold.token:
                continue
            totals["changed_tokens"] += 1

            apply_tok = apply_rows[idx].token if idx < len(apply_rows) else ""
            candidates = source.top_k(inp.token)
            cand_terms = [_norm(c.term) for c in candidates]
            gold_norm = _norm(gold.token)
            has_candidate = bool(candidates)
            gold_in_topk = gold_norm in cand_terms
            selected_gold = _norm(apply_tok) == gold_norm

            local_noise = _local_noise_flags(case.input_text, inp)
            for k, v in {**case_noise, **local_noise}.items():
                if v:
                    noise_counts[k] += 1

            if not _shape_allowed(inp.token):
                slices["token_rejected_before_retrieval"] += 1
                status = "token_rejected_before_retrieval"
            elif not has_candidate and local_noise["wrapper_no_touch_style"]:
                slices["candidate_polluted_by_punctuation_wrappers"] += 1
                status = "candidate_polluted_by_punctuation_wrappers"
            elif not has_candidate and local_noise["mixed_alnum_non_ru_shape"]:
                slices["no_candidate_due_to_token_shape"] += 1
                status = "no_candidate_due_to_token_shape"
            elif has_candidate and not gold_in_topk:
                slices["candidate_exists_but_gold_absent_topk"] += 1
                status = "candidate_exists_but_gold_absent_topk"
            elif gold_in_topk and not selected_gold:
                slices["gold_present_in_topk_but_not_selected"] += 1
                status = "gold_present_in_topk_but_not_selected"
            elif not has_candidate:
                slices["other"] += 1
                status = "other"
            else:
                status = "selected"

            if any(case_noise.values()) or any(local_noise.values()):
                totals["noise_changed_tokens"] += 1
                noise_break["any_candidate"]["yes" if has_candidate else "no"] += 1
                noise_break["gold_in_topk"]["yes" if gold_in_topk else "no"] += 1
                if gold_in_topk:
                    noise_break["selected_when_gold_in_topk"]["selected" if selected_gold else "not_selected"] += 1

            if status != "selected":
                for k, v in {**case_noise, **local_noise}.items():
                    if v:
                        noise_break[k][status] += 1

            stripped = re.sub(r"[^\w-]", "", inp.token, flags=re.UNICODE)
            if _shape_allowed(inp.token):
                normalization["baseline_gold_in_topk"] += int(gold_in_topk)
            if bool(source.top_k(inp.token.lower())) and gold_norm in [_norm(c.term) for c in source.top_k(inp.token.lower())]:
                normalization["lowercase_gold_in_topk"] += 1
            if bool(source.top_k(inp.token.replace("ё", "е").replace("Ё", "Е"))) and gold_norm in [_norm(c.term) for c in source.top_k(inp.token.replace("ё", "е").replace("Ё", "Е"))]:
                normalization["yo_to_e_gold_in_topk"] += 1
            if stripped and bool(source.top_k(stripped)) and gold_norm in [_norm(c.term) for c in source.top_k(stripped)]:
                normalization["strip_punct_gold_in_topk"] += 1
            cleaned = re.sub(r"(.)\1{2,}", r"\1\1", stripped.lower())
            if cleaned and bool(source.top_k(cleaned)) and gold_norm in [_norm(c.term) for c in source.top_k(cleaned)]:
                normalization["chat_noise_cleanup_gold_in_topk"] += 1

            if status in {
                "candidate_polluted_by_punctuation_wrappers",
                "gold_present_in_topk_but_not_selected",
                "token_rejected_before_retrieval",
                "candidate_exists_but_gold_absent_topk",
            } and len(examples[status]) < 5:
                examples[status].append(
                    {
                        "input_text": case.input_text,
                        "input_token": inp.token,
                        "gold_token": gold.token,
                        "current_apply_token": apply_tok,
                        "top_k": cand_terms[:5],
                        "noise_flags": {k: v for k, v in {**case_noise, **local_noise}.items() if v},
                    }
                )

    changed_tokens = max(1, totals["changed_tokens"])
    ranked = sorted(slices.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "dataset": str(corpus_path),
        "expected_change_cases": totals["expected_change_cases"],
        "changed_tokens": totals["changed_tokens"],
        "candidate_source_failure_slices": {
            k: {"count": v, "rate_over_changed_tokens": v / changed_tokens} for k, v in ranked
        },
        "punctuation_noise_audit": {
            "class_frequency": dict(noise_counts),
            "retrieval_selection_breakdown": {k: dict(v) for k, v in noise_break.items()},
        },
        "token_normalization_audit": {
            "notes": "diagnosis-only retrieval probes; original token is preserved for apply path",
            "gold_in_topk_probe_counts": dict(normalization),
        },
        "gold_in_topk_under_noise": {
            "noise_changed_tokens": totals["noise_changed_tokens"],
            "any_candidate_coverage": dict(noise_break.get("any_candidate", {})),
            "gold_in_topk_coverage": dict(noise_break.get("gold_in_topk", {})),
            "selected_vs_not_selected_when_gold_in_topk": dict(noise_break.get("selected_when_gold_in_topk", {})),
        },
        "representative_examples": dict(examples),
        "ranked_root_causes": [{"name": k, "count": v} for k, v in ranked],
    }


def run_audit(output_path: Path) -> dict[str, Any]:
    base_cfg = {
        "dictionary_source": "app/resources/ru_dictionary_v7.txt",
        "extra_dictionary_sources": ["research/context_rerank_v1/resources/ru_wordfreq_top50k.txt"],
        "top_k": 5,
        "max_edit_distance": 3,
    }
    payload = {
        "full_public": _analyze_dataset(Path("tests/cases/ruspellgold_full_public.jsonl"), base_cfg),
        "holdout": _analyze_dataset(Path("tests/cases/product_regression_user_texts.yml"), base_cfg),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Candidate and punctuation root-cause audit")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("research/context_rerank_v1/candidate_punctuation_root_cause_audit.json"),
    )
    args = parser.parse_args()
    run_audit(args.output_json)


if __name__ == "__main__":
    main()
