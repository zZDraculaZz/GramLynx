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


def test_metrics_enabled_exposes_endpoint(monkeypatch, tmp_path) -> None:
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("сегодня\n", encoding="utf-8")
    cfg = tmp_path / "metrics_rulepack.yml"
    cfg.write_text(
        f"""
policies:
  smart:
    enabled_stages: [s1_normalize, s2_segment, s3_spelling, s6_guardrails, s7_assemble]
    max_changed_char_ratio: 1.0
rulepack:
  enable_candidate_generation_ru: true
  candidate_backend: rapidfuzz
  dictionary_source_ru: {dictionary}
  typo_map_smart_ru: {{}}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(cfg))
    client = _build_client(monkeypatch, enabled=True)

    # Generate some metric activity first.
    client.post("/clean", json={"text": "севодня", "mode": "smart"})
    client.post("/clean", json={"text": "Ссылка: https://example.com", "mode": "strict"})

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "http_request" in body
    assert "gramlynx_rollbacks_total" in body
    assert "gramlynx_pz_spans_total" in body
    assert "gramlynx_candidate_generated_total" in body
    assert "gramlynx_candidate_applied_total" in body
    assert "gramlynx_candidate_rejected_total" in body
    assert "gramlynx_candidate_ambiguous_total" in body


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
