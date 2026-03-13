"""Детерминированные орфографические замены (без угадываний)."""
from __future__ import annotations

import importlib
import importlib.util
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


REPLACEMENTS = {
    "жы": "жи",
    "Жы": "Жи",
    "ЖЫ": "ЖИ",
    "шы": "ши",
    "Шы": "Ши",
    "ШЫ": "ШИ",
    "чя": "ча",
    "Чя": "Ча",
    "ЧЯ": "ЧА",
    "щя": "ща",
    "Щя": "Ща",
    "ЩЯ": "ЩА",
    "жя": "жа",
    "Жя": "Жа",
    "ЖЯ": "ЖА",
    "чю": "чу",
    "Чю": "Чу",
    "ЧЮ": "ЧУ",
    "щю": "щу",
    "Щю": "Щу",
    "ЩЮ": "ЩУ",
    "жю": "жу",
    "Жю": "Жу",
    "ЖЮ": "ЖУ",
    "шю": "шу",
    "Шю": "Шу",
    "ШЮ": "ШУ",
}


@dataclass(frozen=True)
class ReplacementEdit:
    """Кандидат правки для детерминированных замен."""

    start: int
    end: int
    before: str
    after: str


@dataclass(frozen=True)
class MorphSafetyStats:
    """Безопасные счётчики решений morph safety-layer."""

    morph_blocked_count: int = 0
    morph_allowed_count: int = 0
    morph_unknown_count: int = 0


@dataclass(frozen=True)
class CandidateStats:
    """Безопасные счётчики candidate generation (fallback path)."""

    candidate_generated_count: int = 0
    candidate_applied_count: int = 0
    candidate_rejected_count: int = 0
    candidate_ambiguous_count: int = 0
    candidate_rejected_no_result_count: int = 0
    candidate_rejected_unsafe_candidate_count: int = 0
    candidate_rejected_morph_blocked_count: int = 0
    candidate_rejected_morph_unknown_count: int = 0
    candidate_ambiguous_tie_count: int = 0
    candidate_shadow_skipped_count: int = 0


@dataclass(frozen=True)
class ReplacementResult:
    """Результат отбора кандидатов с безопасной статистикой."""

    edits: list[ReplacementEdit]
    morph_stats: MorphSafetyStats
    candidate_stats: CandidateStats


def find_replacements(text: str) -> list[ReplacementEdit]:
    """Ищет базовые детерминированные замены в тексте (legacy)."""

    edits: list[ReplacementEdit] = []
    for wrong, right in REPLACEMENTS.items():
        for match in re.finditer(re.escape(wrong), text):
            edits.append(
                ReplacementEdit(
                    start=match.start(),
                    end=match.end(),
                    before=wrong,
                    after=right,
                )
            )
    edits.sort(key=lambda item: (item.start, item.end))
    return edits


def find_rulepack_replacements(
    text: str,
    typo_map: dict[str, str],
    min_token_len: int,
    allowlist: set[str],
    denylist: set[str],
    no_touch_tokens: set[str] | None = None,
    no_touch_prefixes: tuple[str, ...] = (),
    enable_morph_safety_ru: bool = False,
    enable_candidate_generation_ru: bool = False,
    candidate_shadow_mode_ru: bool = False,
    candidate_backend: str = "none",
    max_candidates_ru: int = 3,
    max_edit_distance_ru: int = 1,
    dictionary_source_ru: str = "",
) -> ReplacementResult:
    """Token-level replacements from rulepack typo_map with strict guards."""

    if not typo_map and not enable_candidate_generation_ru:
        return ReplacementResult(
            edits=[],
            morph_stats=MorphSafetyStats(),
            candidate_stats=CandidateStats(),
        )

    edits: list[ReplacementEdit] = []
    no_touch = no_touch_tokens or set()
    pattern = re.compile(r"\b[\w-]{%d,}\b" % max(min_token_len, 1), flags=re.UNICODE)
    morph_blocked_count = 0
    morph_allowed_count = 0
    morph_unknown_count = 0
    candidate_generated_count = 0
    candidate_applied_count = 0
    candidate_rejected_count = 0
    candidate_ambiguous_count = 0
    candidate_rejected_no_result_count = 0
    candidate_rejected_unsafe_candidate_count = 0
    candidate_rejected_morph_blocked_count = 0
    candidate_rejected_morph_unknown_count = 0
    candidate_ambiguous_tie_count = 0
    candidate_shadow_skipped_count = 0

    analyzer = _get_morph_analyzer() if enable_morph_safety_ru else None

    for match in pattern.finditer(text):
        token = match.group(0)
        if not _safe_ru_token(token):
            continue
        if token in no_touch:
            continue
        if no_touch_prefixes and match.start() > 0 and text[match.start() - 1] in no_touch_prefixes:
            continue
        if _is_sensitive_wrapped_token(text, match.start(), match.end(), no_touch_prefixes):
            continue
        if token in allowlist or token in denylist:
            continue

        replacement = typo_map.get(token)
        from_generator = False

        if not replacement and enable_candidate_generation_ru:
            candidate = None
            status = "rejected"
            if candidate_backend == "rapidfuzz":
                candidate, status = _candidate_from_rapidfuzz(
                    token=token,
                    max_candidates=max_candidates_ru,
                    max_edit_distance=max_edit_distance_ru,
                    dictionary_source=dictionary_source_ru,
                )
            elif candidate_backend == "symspell":
                candidate, status = _candidate_from_symspell(
                    token=token,
                    max_candidates=max_candidates_ru,
                    max_edit_distance=max_edit_distance_ru,
                    dictionary_source=dictionary_source_ru,
                )

            if status == "ambiguous":
                candidate_ambiguous_count += 1
                candidate_ambiguous_tie_count += 1
            elif status == "rejected":
                candidate_rejected_count += 1
                candidate_rejected_no_result_count += 1
            elif status == "generated" and candidate:
                candidate_generated_count += 1
                replacement = candidate
                from_generator = True

        if not replacement or replacement == token:
            continue
        if not _safe_candidate_token(replacement):
            if from_generator:
                candidate_rejected_count += 1
                candidate_rejected_unsafe_candidate_count += 1
            continue

        if enable_morph_safety_ru and analyzer is not None:
            decision = _morph_decision_ru(token, replacement, analyzer)
            if decision == "allowed":
                morph_allowed_count += 1
            elif decision == "blocked":
                morph_blocked_count += 1
                if from_generator:
                    candidate_rejected_count += 1
                    candidate_rejected_morph_blocked_count += 1
                continue
            else:
                morph_unknown_count += 1
                if from_generator:
                    candidate_rejected_count += 1
                    candidate_rejected_morph_unknown_count += 1
                continue

        if from_generator and candidate_shadow_mode_ru:
            candidate_shadow_skipped_count += 1
            continue

        edits.append(
            ReplacementEdit(
                start=match.start(),
                end=match.end(),
                before=token,
                after=replacement,
            )
        )
        if from_generator:
            candidate_applied_count += 1

    edits.sort(key=lambda item: (item.start, item.end))
    return ReplacementResult(
        edits=edits,
        morph_stats=MorphSafetyStats(
            morph_blocked_count=morph_blocked_count,
            morph_allowed_count=morph_allowed_count,
            morph_unknown_count=morph_unknown_count,
        ),
        candidate_stats=CandidateStats(
            candidate_generated_count=candidate_generated_count,
            candidate_applied_count=candidate_applied_count,
            candidate_rejected_count=candidate_rejected_count,
            candidate_ambiguous_count=candidate_ambiguous_count,
            candidate_rejected_no_result_count=candidate_rejected_no_result_count,
            candidate_rejected_unsafe_candidate_count=candidate_rejected_unsafe_candidate_count,
            candidate_rejected_morph_blocked_count=candidate_rejected_morph_blocked_count,
            candidate_rejected_morph_unknown_count=candidate_rejected_morph_unknown_count,
            candidate_ambiguous_tie_count=candidate_ambiguous_tie_count,
            candidate_shadow_skipped_count=candidate_shadow_skipped_count,
        ),
    )


def _safe_ru_token(token: str) -> bool:
    if "-" in token:
        return False
    if any(char.isdigit() for char in token):
        return False
    has_cyr = any("а" <= ch <= "я" or ch == "ё" or "А" <= ch <= "Я" or ch == "Ё" for ch in token)
    has_latin = any("a" <= ch.lower() <= "z" for ch in token)
    if has_latin or not has_cyr:
        return False
    # no-touch for name/brand-like tokens
    if any(ch.isupper() for ch in token):
        return False
    return bool(re.fullmatch(r"[а-яё]+", token))


def _safe_candidate_token(token: str) -> bool:
    if not token or " " in token:
        return False
    if token.startswith("-") or token.endswith("-") or "--" in token:
        return False
    if any(char.isdigit() for char in token):
        return False
    if any("a" <= ch.lower() <= "z" for ch in token):
        return False
    if any(ch.isupper() for ch in token):
        return False
    return bool(re.fullmatch(r"[а-яё-]+", token))


def _candidate_from_rapidfuzz(
    token: str,
    max_candidates: int,
    max_edit_distance: int,
    dictionary_source: str,
) -> tuple[str | None, str]:
    try:
        from rapidfuzz import fuzz, process
        from rapidfuzz.distance import Levenshtein
    except Exception:
        return None, "rejected"

    words = _load_ru_dictionary(dictionary_source)
    if not words:
        return None, "rejected"

    limit = max(1, max_candidates)
    matches = process.extract(token, words, scorer=fuzz.ratio, limit=limit)
    if not matches:
        return None, "rejected"

    filtered: list[tuple[str, float, int]] = []
    for candidate, score, _ in matches:
        if candidate == token or not _safe_candidate_token(candidate):
            continue
        dist = int(Levenshtein.distance(token, candidate))
        if dist <= max_edit_distance:
            filtered.append((candidate, float(score), dist))

    if not filtered:
        return None, "rejected"

    filtered.sort(key=lambda item: (item[2], -item[1], item[0]))
    best = filtered[0]
    if len(filtered) > 1:
        second = filtered[1]
        if (best[2], best[1]) == (second[2], second[1]):
            return None, "ambiguous"

    return best[0], "generated"


@lru_cache(maxsize=4)
def _load_ru_dictionary(dictionary_source: str) -> tuple[str, ...]:
    source = dictionary_source.strip() if dictionary_source else ""
    if source:
        path = Path(source)
    else:
        path = Path(__file__).resolve().parents[3] / "resources" / "ru_dictionary_v1.txt"
    if not path.exists():
        return ()

    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        if _safe_candidate_token(word):
            words.append(word)
    return tuple(dict.fromkeys(words))






def _candidate_from_symspell(
    token: str,
    max_candidates: int,
    max_edit_distance: int,
    dictionary_source: str,
) -> tuple[str | None, str]:
    try:
        from symspellpy import Verbosity
    except Exception:
        return None, "rejected"

    symspell = _get_symspell(dictionary_source)
    if symspell is None:
        return None, "rejected"

    try:
        suggestions = symspell.lookup(
            token,
            Verbosity.CLOSEST,
            max_edit_distance=max_edit_distance,
            include_unknown=False,
            transfer_casing=False,
        )
    except Exception:
        return None, "rejected"

    if not suggestions:
        return None, "rejected"

    filtered: list[tuple[str, int, int]] = []
    for suggestion in suggestions[: max(1, max_candidates)]:
        term = suggestion.term
        if term == token or not _safe_candidate_token(term):
            continue
        dist = int(suggestion.distance)
        if dist <= max_edit_distance:
            filtered.append((term, dist, int(suggestion.count)))

    if not filtered:
        return None, "rejected"

    filtered.sort(key=lambda item: (item[1], -item[2], item[0]))
    best = filtered[0]
    if len(filtered) > 1:
        second = filtered[1]
        if (best[1], best[2]) == (second[1], second[2]):
            return None, "ambiguous"

    return best[0], "generated"
@lru_cache(maxsize=4)
def _get_symspell(dictionary_source: str):
    try:
        from symspellpy import SymSpell
    except Exception:
        return None

    words = _load_ru_dictionary(dictionary_source)
    if not words:
        return None

    symspell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
    for rank, word in enumerate(words):
        # deterministic pseudo-frequency: earlier words get higher count
        count = max(1, len(words) - rank)
        symspell.create_dictionary_entry(word, count)
    return symspell


def _is_sensitive_wrapped_token(
    text: str,
    start: int,
    end: int,
    no_touch_prefixes: tuple[str, ...],
) -> bool:
    """Conservative blocker for context-sensitive wrapped/key-like tokens."""

    prev_char = text[start - 1] if start > 0 else ""
    next_char = text[end] if end < len(text) else ""
    before_prev = text[start - 2] if start > 1 else ""

    # (token), "token", /token/
    if prev_char == "(" and next_char == ")":
        return True
    if prev_char in {'"', "'"} and next_char == prev_char:
        return True
    if prev_char == "/" and next_char == "/":
        return True

    # key:token or key_token (identifier-like glue)
    if prev_char in {":", "_"} and (before_prev.isalnum() or before_prev == "_"):
        return True

    # Explicit no-touch prefixes also treated as wrappers.
    if prev_char and prev_char in no_touch_prefixes:
        return True

    return False


def _morph_decision_ru(before: str, after: str, analyzer: Any) -> str:
    before_parses = analyzer.parse(before)
    after_parses = analyzer.parse(after)
    if not before_parses or not after_parses:
        return "unknown"

    before_known = any(getattr(parse, "is_known", False) for parse in before_parses)
    after_known = any(getattr(parse, "is_known", False) for parse in after_parses)
    before_score = max(float(getattr(parse, "score", 0.0)) for parse in before_parses)
    after_score = max(float(getattr(parse, "score", 0.0)) for parse in after_parses)

    # Conservative blocker: if source already looks morphologically valid, do not auto-correct.
    if before_known and before_score >= 0.25:
        return "blocked"

    # Allow only when replacement is clearly better and known.
    if after_known and (not before_known or after_score >= before_score + 0.15):
        return "allowed"

    return "unknown"


@lru_cache(maxsize=1)
def _get_morph_analyzer() -> Any | None:
    if importlib.util.find_spec("pymorphy3") is None:
        return None
    module = importlib.import_module("pymorphy3")
    return module.MorphAnalyzer()
