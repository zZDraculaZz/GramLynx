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

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_request" in response.text


def test_metrics_disabled_returns_404(monkeypatch) -> None:
    client = _build_client(monkeypatch, enabled=False)

    response = client.get("/metrics")

    assert response.status_code == 404
