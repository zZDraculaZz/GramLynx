"""Protected zones detector."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.core.model import ProtectedSpan
from app.core.protected_zones.patterns import PATTERNS

PLACEHOLDER_TEMPLATE = "⟦PZ{index}⟧"


def _find_spans(text: str) -> List[ProtectedSpan]:
    spans: List[ProtectedSpan] = []
    for label, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            spans.append(
                ProtectedSpan(
                    start=match.start(),
                    end=match.end(),
                    label=label,
                    source="regex",
                )
            )
    return spans


def _merge_spans(spans: List[ProtectedSpan]) -> List[ProtectedSpan]:
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (s.start, s.end))
    merged = [sorted_spans[0]]
    for span in sorted_spans[1:]:
        last = merged[-1]
        if span.start <= last.end:
            merged[-1] = ProtectedSpan(
                start=last.start,
                end=max(last.end, span.end),
                label=last.label,
                source=last.source,
            )
        else:
            merged.append(span)
    return merged


def mask_protected_zones(text: str) -> Tuple[str, Dict[str, str], List[ProtectedSpan]]:
    spans = _merge_spans(_find_spans(text))
    placeholders: Dict[str, str] = {}
    masked = text
    offset = 0
    for index, span in enumerate(spans):
        placeholder = PLACEHOLDER_TEMPLATE.format(index=index)
        start = span.start + offset
        end = span.end + offset
        original = masked[start:end]
        placeholders[placeholder] = original
        masked = masked[:start] + placeholder + masked[end:]
        offset += len(placeholder) - (end - start)
    return masked, placeholders, spans


def restore_protected_zones(text: str, placeholders: Dict[str, str]) -> str:
    restored = text
    for placeholder, original in placeholders.items():
        restored = restored.replace(placeholder, original)
    return restored


def placeholders_intact(text: str, placeholders: Dict[str, str]) -> bool:
    return all(placeholder in text for placeholder in placeholders)


def count_placeholders(text: str) -> int:
    return len(re.findall(r"⟦PZ\d+⟧", text))
