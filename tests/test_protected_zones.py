"""Protected zones tests."""
from __future__ import annotations

from app.core.protected_zones.detector import mask_protected_zones, restore_protected_zones


def test_mask_restore_roundtrip() -> None:
    text = "Почта test@example.com и ссылка https://example.com"
    masked, placeholders, _ = mask_protected_zones(text)
    restored = restore_protected_zones(masked, placeholders)
    assert restored == text
