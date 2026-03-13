"""Tests for request max body size middleware."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _build_client(monkeypatch, max_body: str | None) -> TestClient:
    monkeypatch.delenv("GRAMLYNX_ENABLE_METRICS", raising=False)
    if max_body is None:
        monkeypatch.delenv("GRAMLYNX_MAX_BODY_BYTES", raising=False)
    else:
        monkeypatch.setenv("GRAMLYNX_MAX_BODY_BYTES", max_body)

    import app.main as app_main

    reloaded = importlib.reload(app_main)
    return TestClient(reloaded.app)


def test_small_request_passes(monkeypatch) -> None:
    client = _build_client(monkeypatch, max_body="2048")

    response = client.post("/clean", json={"text": "Привет мир", "mode": "strict"})

    assert response.status_code == 200
    assert list(response.json().keys()) == ["clean_text"]


def test_request_larger_than_limit_returns_413(monkeypatch) -> None:
    client = _build_client(monkeypatch, max_body="128")
    huge_text = "A" * 5000

    response = client.post("/clean", json={"text": huge_text, "mode": "strict"})

    assert response.status_code == 413


def test_default_limit_used_when_env_missing(monkeypatch) -> None:
    client = _build_client(monkeypatch, max_body=None)
    huge_text = "B" * (1_200_000)

    response = client.post("/clean", json={"text": huge_text, "mode": "strict"})

    assert response.status_code == 413
