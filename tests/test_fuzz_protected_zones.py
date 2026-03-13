"""Property-based fuzz tests for Protected Zones and rollback invariants."""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.core.orchestrator import Orchestrator
from app.core.protected_zones.detector import PLACEHOLDER_TEMPLATE


def _protected_chunk(seed: int) -> str:
    i = abs(seed)
    kind = i % 11
    if kind == 0:
        return f"https://example{i}.com/path/{i}?q={i}"
    if kind == 1:
        return f"user{i}@mail{i}.example"
    if kind == 2:
        return f"550e8400-e29b-41d4-a716-{i % 1_000_000_000_000:012d}"
    if kind == 3:
        return f"AB-{i % 999999:06d}"
    if kind == 4:
        return f"{(i % 28) + 1:02d}.{(i % 12) + 1:02d}.20{(i % 90) + 10:02d}"
    if kind == 5:
        return f"{(i % 24):02d}:{(i % 60):02d}"
    if kind == 6:
        return f"{i % 1_000_000}"
    if kind == 7:
        return f"C:\\Temp\\trace_{i}.log"
    if kind == 8:
        return f"git commit -m msg{i}"
    if kind == 9:
        return f"```sql\nSELECT id FROM users WHERE id = {i};\n```"
    return (
        "<code>Traceback (most recent call last):\n"
        f'  File "main_{i}.py", line {(i % 97) + 1}, in <module>\n'
        f"ValueError: boom{i}</code>"
    )


def _run_clean(text: str, mode: str = "smart") -> str:
    return Orchestrator(correlation_id="fuzz").clean(text=text, mode=mode)


@settings(max_examples=80, deadline=None)
@given(
    seeds=st.lists(
        st.integers(min_value=0, max_value=10_000),
        min_size=1,
        max_size=7,
        unique=True,
    )
)
def test_fuzz_protected_zone_fragments_survive_byte_to_byte(seeds: list[int]) -> None:
    chunks = [_protected_chunk(seed) for seed in seeds]
    text = "Префикс: " + " | ".join(chunks) + " :суффикс"

    clean_text = _run_clean(text)

    for chunk in chunks:
        assert chunk in clean_text


@settings(max_examples=60, deadline=None)
@given(
    seeds=st.lists(
        st.integers(min_value=0, max_value=10_000),
        min_size=1,
        max_size=8,
        unique=True,
    )
)
def test_fuzz_no_placeholder_markers_left_in_output(seeds: list[int]) -> None:
    placeholder_prefix = PLACEHOLDER_TEMPLATE.split("{index}")[0]
    chunks = [_protected_chunk(seed) for seed in seeds]
    text = "Начало " + " ; ".join(chunks) + " Конец"

    clean_text = _run_clean(text)

    assert placeholder_prefix not in clean_text


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(min_value=1, max_value=10_000), mode=st.sampled_from(["strict", "smart"]))
def test_fuzz_poison_patterns_near_protected_zone_stay_safe(seed: int, mode: str) -> None:
    url = f"https://example{seed}.com/path/{seed}"
    email = f"user{seed}@mail{seed}.example"
    templates = [
        f"Ссылка: {url},ok?",
        f"Почта: {email},ok?",
        f"жыжы {url} жыжы",
    ]
    placeholder_prefix = PLACEHOLDER_TEMPLATE.split("{index}")[0]

    for text in templates:
        clean_text = _run_clean(text, mode=mode)
        assert url in clean_text or email in clean_text
        assert placeholder_prefix not in clean_text
        assert clean_text == text
