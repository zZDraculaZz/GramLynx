"""Product-oriented golden regression pack for user-like RU texts."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.config import reset_app_config_cache
from app.core.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _reset_config_cache_between_tests() -> None:
    reset_app_config_cache()
    yield
    reset_app_config_cache()


def _load_cases() -> list[dict[str, str]]:
    data = yaml.safe_load(Path("tests/cases/product_regression_user_texts.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    items = data.get("smart")
    assert isinstance(items, list)
    return items


def test_product_regression_pack_user_like_ru_smart(monkeypatch) -> None:
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(Path("config.example.yml").resolve()))
    reset_app_config_cache()

    for index, case in enumerate(_load_cases(), start=1):
        input_text = case["input"]
        expected = case["expected_clean_text"]
        category = case.get("category", "uncategorized")

        result = Orchestrator(correlation_id=f"product-regression-{index}").clean(input_text, mode="smart")
        assert result == expected, f"case#{index} category={category}"
