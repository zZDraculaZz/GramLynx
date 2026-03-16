from __future__ import annotations

import json
from pathlib import Path

from research.context_rerank_v1.candidate_source import LargeLexiconCandidateSource
from research.context_rerank_v1.replay import TOKEN_RE, ReplayCase, _run_current_apply, load_cases


def norm(token: str) -> str:
    return token.strip().lower().replace("ё", "е")


def compute(corpus_path: Path, enabled: bool) -> dict[str, int]:
    src = LargeLexiconCandidateSource(
        dictionary_path="app/resources/ru_dictionary_v7.txt",
        top_k=5,
        max_edit_distance=3,
        extra_dictionary_paths=("research/context_rerank_v1/resources/ru_wordfreq_top50k.txt",),
        enable_retrieval_normalization=enabled,
    )
    cases = load_cases(corpus_path)
    current_apply = _run_current_apply(tuple(ReplayCase(c.input_text, c.expected_clean_text) for c in cases))

    expected_change_cases = 0
    cases_with_any_candidate = 0
    cases_with_gold_in_topk = 0
    changed_tokens = 0
    no_candidate = 0
    cand_exists_gold_absent = 0
    gold_present_not_selected = 0
    seg_mismatch = 0
    punct_wrapper_fail = 0

    for case in cases:
        if case.input_text == case.expected_clean_text:
            continue
        expected_change_cases += 1
        inp = TOKEN_RE.findall(case.input_text)
        exp = TOKEN_RE.findall(case.expected_clean_text)
        app = TOKEN_RE.findall(current_apply[case.input_text].output)
        if len(inp) != len(exp):
            seg_mismatch += 1
            continue
        case_any = False
        case_gold = False
        for idx, (i, g) in enumerate(zip(inp, exp)):
            if i == g:
                continue
            changed_tokens += 1
            top = src.top_k(i)
            terms = [norm(c.term) for c in top]
            gold = norm(g)
            apply_tok = norm(app[idx]) if idx < len(app) else ""

            if top:
                case_any = True
            else:
                no_candidate += 1
                # very narrow punctuation/wrapper proxy
                if any(ch in case.input_text for ch in "`*_~[](){}"):
                    punct_wrapper_fail += 1
            if gold in terms:
                case_gold = True
                if apply_tok != gold:
                    gold_present_not_selected += 1
            elif top:
                cand_exists_gold_absent += 1
        cases_with_any_candidate += int(case_any)
        cases_with_gold_in_topk += int(case_gold)

    return {
        "expected_change_cases": expected_change_cases,
        "changed_tokens": changed_tokens,
        "cases_with_any_candidate": cases_with_any_candidate,
        "cases_with_gold_in_topk": cases_with_gold_in_topk,
        "no_candidate_count": no_candidate,
        "candidate_exists_but_gold_absent_topk": cand_exists_gold_absent,
        "gold_present_in_topk_but_not_selected": gold_present_not_selected,
        "segmentation_tokenization_mismatch": seg_mismatch,
        "punctuation_wrapper_related_failure_count": punct_wrapper_fail,
    }


payload = {
    "full_public": {
        "before": compute(Path("tests/cases/ruspellgold_full_public.jsonl"), False),
        "after": compute(Path("tests/cases/ruspellgold_full_public.jsonl"), True),
    },
    "holdout": {
        "before": compute(Path("tests/cases/product_regression_user_texts.yml"), False),
        "after": compute(Path("tests/cases/product_regression_user_texts.yml"), True),
    },
}
Path("research/context_rerank_v1/retrieval_coverage_comparison.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print("done")
