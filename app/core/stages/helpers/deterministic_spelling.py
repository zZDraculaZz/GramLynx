"""Детерминированные орфографические замены (без угадываний)."""
from __future__ import annotations

import re
from dataclasses import dataclass


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
) -> list[ReplacementEdit]:
    """Token-level replacements from rulepack typo_map with strict guards."""

    if not typo_map:
        return []

    edits: list[ReplacementEdit] = []
    pattern = re.compile(r"\b[а-яё]{%d,}\b" % max(min_token_len, 1))

    for match in pattern.finditer(text):
        token = match.group(0)
        if token in allowlist or token in denylist:
            continue
        replacement = typo_map.get(token)
        if not replacement or replacement == token:
            continue
        edits.append(
            ReplacementEdit(
                start=match.start(),
                end=match.end(),
                before=token,
                after=replacement,
            )
        )

    edits.sort(key=lambda item: (item.start, item.end))
    return edits
