from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.stages.helpers import deterministic_spelling as canonical_spelling
from research.context_rerank_v1.candidate_source import Candidate, LargeLexiconCandidateSource, _levenshtein_distance
from research.context_rerank_v1.replay import _load_cases_jsonl, _load_cases_yaml

TOKEN_RE = re.compile(r"\b[\w-]+\b", flags=re.UNICODE)


@dataclass(frozen=True)
class LegacyCandidateSource:
    dictionary_path: Path
    top_k_size: int = 5
    max_edit_distance: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "_symspell", self._build_symspell(self.dictionary_path))
        object.__setattr__(self, "_terms", self._load_terms(self.dictionary_path) if self._symspell is None else tuple())

    @staticmethod
    def _build_symspell(path: Path) -> Any | None:
        try:
            from symspellpy import SymSpell
        except Exception:
            return None
        if not path.exists():
            return None
        symspell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        loaded = symspell.load_dictionary(str(path), term_index=0, count_index=1, separator="\t")
        if not loaded:
            for line in path.read_text(encoding="utf-8").splitlines():
                token = line.strip().lower()
                if token:
                    symspell.create_dictionary_entry(token, 1)
        return symspell

    @staticmethod
    def _load_terms(path: Path) -> tuple[str, ...]:
        terms: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            token = line.split("\t", maxsplit=1)[0].strip().lower()
            if token:
                terms.append(token)
        return tuple(dict.fromkeys(terms))

    def top_k(self, token: str) -> tuple[Candidate, ...]:
        token_norm = token.strip().lower()
        if not token_norm:
            return tuple()
        if self._symspell is not None:
            from symspellpy import Verbosity

            suggestions = self._symspell.lookup(
                token_norm,
                Verbosity.CLOSEST,
                max_edit_distance=self.max_edit_distance,
                include_unknown=False,
                transfer_casing=False,
            )
            out = [Candidate(term=s.term, distance=int(s.distance)) for s in suggestions if s.term != token_norm]
            return tuple(out[: self.top_k_size])

        if token_norm in self._terms:
            return tuple()
        scored: list[Candidate] = []
        for term in self._terms:
            dist = _levenshtein_distance(token_norm, term)
            if dist <= self.max_edit_distance:
                scored.append(Candidate(term=term, distance=dist))
        scored.sort(key=lambda item: (item.distance, abs(len(item.term) - len(token_norm)), item.term))
        return tuple(scored[: self.top_k_size])


def _load_cases(path: Path) -> list[tuple[str, str]]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        return [(row.input_text, row.expected_clean_text) for row in _load_cases_yaml(path)]
    return [(row.input_text, row.expected_clean_text) for row in _load_cases_jsonl(path)]


def _analyze(config_path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    corpus_path = Path(str(cfg["corpus_path"]))
    dictionary_path = Path(str(cfg["dictionary_source"]))
    top_k = int(cfg.get("top_k", 5))

    cases = _load_cases(corpus_path)
    legacy = LegacyCandidateSource(dictionary_path=dictionary_path, top_k_size=top_k)
    extra_dictionary_sources = tuple(Path(str(p)) for p in cfg.get("extra_dictionary_sources", []))
    improved = LargeLexiconCandidateSource(
        dictionary_path=dictionary_path,
        top_k=top_k,
        max_edit_distance=int(cfg.get("max_edit_distance", 3)),
        extra_dictionary_paths=tuple(str(p) for p in extra_dictionary_sources),
    )

    expected_change_cases = 0
    legacy_any_candidate_cases = 0
    improved_any_candidate_cases = 0
    legacy_gold_in_topk_cases = 0
    improved_gold_in_topk_cases = 0

    mismatch_main_yes_research_no = 0
    mismatch_research_yes_main_no = 0
    topk_overlap_with_main_best = 0

    root_causes = {
        "token_not_safe_ru": 0,
        "legacy_no_candidate_improved_has_candidate": 0,
        "both_no_candidate": 0,
        "gold_absent_in_both": 0,
    }

    for input_text, expected_text in cases:
        inp_tokens = TOKEN_RE.findall(input_text)
        exp_tokens = TOKEN_RE.findall(expected_text)
        changed_positions = [i for i, (a, b) in enumerate(zip(inp_tokens, exp_tokens)) if a != b]
        if not changed_positions:
            continue

        expected_change_cases += 1
        case_legacy_any = False
        case_improved_any = False
        case_legacy_gold = False
        case_improved_gold = False

        for idx in changed_positions:
            token = inp_tokens[idx]
            gold = exp_tokens[idx].lower().replace("ё", "е")
            legacy_topk = [c.term for c in legacy.top_k(token)]
            improved_topk = [c.term for c in improved.top_k(token)]

            main_candidate, main_status = canonical_spelling._candidate_from_symspell(
                token=token.lower(),
                max_candidates=top_k,
                max_edit_distance=3,
                dictionary_source=str(dictionary_path),
            )
            main_has_candidate = main_status == "generated" and bool(main_candidate)

            if main_has_candidate and not improved_topk:
                mismatch_main_yes_research_no += 1
            if improved_topk and not main_has_candidate:
                mismatch_research_yes_main_no += 1
            if main_has_candidate and main_candidate in improved_topk:
                topk_overlap_with_main_best += 1

            if legacy_topk:
                case_legacy_any = True
            if improved_topk:
                case_improved_any = True
            if gold in legacy_topk:
                case_legacy_gold = True
            if gold in improved_topk:
                case_improved_gold = True

            if not re.fullmatch(r"[а-яё-]+", token.lower()):
                root_causes["token_not_safe_ru"] += 1
            if not legacy_topk and improved_topk:
                root_causes["legacy_no_candidate_improved_has_candidate"] += 1
            if not legacy_topk and not improved_topk:
                root_causes["both_no_candidate"] += 1
            if gold not in legacy_topk and gold not in improved_topk:
                root_causes["gold_absent_in_both"] += 1

        legacy_any_candidate_cases += int(case_legacy_any)
        improved_any_candidate_cases += int(case_improved_any)
        legacy_gold_in_topk_cases += int(case_legacy_gold)
        improved_gold_in_topk_cases += int(case_improved_gold)

    def _rate(part: int, total: int) -> float:
        return float(part / total) if total else 0.0

    return {
        "dataset": str(corpus_path),
        "dictionary_source": str(dictionary_path),
        "top_k": top_k,
        "expected_change_cases": expected_change_cases,
        "coverage": {
            "legacy": {
                "cases_with_any_candidate": legacy_any_candidate_cases,
                "cases_with_any_candidate_rate": _rate(legacy_any_candidate_cases, expected_change_cases),
                "cases_with_gold_in_topk": legacy_gold_in_topk_cases,
                "cases_with_gold_in_topk_rate": _rate(legacy_gold_in_topk_cases, expected_change_cases),
            },
            "improved": {
                "cases_with_any_candidate": improved_any_candidate_cases,
                "cases_with_any_candidate_rate": _rate(improved_any_candidate_cases, expected_change_cases),
                "cases_with_gold_in_topk": improved_gold_in_topk_cases,
                "cases_with_gold_in_topk_rate": _rate(improved_gold_in_topk_cases, expected_change_cases),
            },
        },
        "candidate_source_mismatch": {
            "main_has_candidate_research_improved_no_candidate": mismatch_main_yes_research_no,
            "research_improved_has_candidate_main_no_candidate": mismatch_research_yes_main_no,
            "main_best_in_research_improved_topk": topk_overlap_with_main_best,
        },
        "root_causes": root_causes,
    }


def main() -> None:
    full = _analyze(Path("research/context_rerank_v1/examples/full_public_pretrained.yaml"))
    holdout = _analyze(Path("research/context_rerank_v1/examples/product_holdout_pretrained.yaml"))
    Path("research/context_rerank_v1/full_public_candidate_diagnostics.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path("research/context_rerank_v1/holdout_candidate_diagnostics.json").write_text(
        json.dumps(holdout, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
