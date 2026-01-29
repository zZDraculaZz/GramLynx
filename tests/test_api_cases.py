"""Smoke-тесты API по выбранным кейсам."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


API_CASES = [
    {
        "name": "strict_no_change_plain",
        "mode": "strict",
        "input_text": "Привет, мир!",
        "expected_clean_text": "Привет, мир!",
    },
    {
        "name": "strict_collapse_spaces",
        "mode": "strict",
        "input_text": "Привет,   мир!",
        "expected_clean_text": "Привет, мир!",
    },
    {
        "name": "smart_basic_spacing_after_punct",
        "mode": "smart",
        "input_text": "Привет,мир!",
        "expected_clean_text": "Привет, мир!",
    },
    {
        "name": "strict_keep_url",
        "mode": "strict",
        "input_text": "Смотри https://example.com/test?x=1&y=2",
        "expected_clean_text": "Смотри https://example.com/test?x=1&y=2",
    },
]


@pytest.mark.parametrize("case", API_CASES, ids=lambda c: c["name"])
def test_api_cases(case: dict) -> None:
    response = client.post("/clean", json={"text": case["input_text"], "mode": case["mode"]})
    assert response.status_code == 200
    payload = response.json()
    assert list(payload.keys()) == ["clean_text"]
    assert payload["clean_text"] == case["expected_clean_text"]
