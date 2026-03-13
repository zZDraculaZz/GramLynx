"""Tests for optional Prometheus metrics endpoint."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _build_client(monkeypatch, enabled: bool) -> TestClient:
    if enabled:
        monkeypatch.setenv("GRAMLYNX_ENABLE_METRICS", "1")
    else:
        monkeypatch.delenv("GRAMLYNX_ENABLE_METRICS", raising=False)

    import app.main as app_main

    reloaded = importlib.reload(app_main)
    return TestClient(reloaded.app)


def test_metrics_enabled_exposes_endpoint(monkeypatch) -> None:
    client = _build_client(monkeypatch, enabled=True)

    # Generate some metric activity first.
    client.post("/clean", json={"text": "A,B,C,D,E", "mode": "smart"})
    client.post("/clean", json={"text": "Ссылка: https://example.com", "mode": "strict"})

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "http_request" in body
    assert "gramlynx_rollbacks_total" in body
    assert "gramlynx_pz_spans_total" in body


def test_metrics_disabled_returns_404(monkeypatch) -> None:
    client = _build_client(monkeypatch, enabled=False)

    response = client.get("/metrics")

    assert response.status_code == 404


def test_metrics_gzip_when_requested(monkeypatch) -> None:
    client = _build_client(monkeypatch, enabled=True)

    response = client.get("/metrics", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") == "gzip"
    assert "gramlynx_pz_spans_total" in response.text
