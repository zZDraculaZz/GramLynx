"""API tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_clean_contract() -> None:
    response = client.post("/clean", json={"text": "Привет мир", "mode": "strict"})
    assert response.status_code == 200
    payload = response.json()
    assert list(payload.keys()) == ["clean_text"]


def test_empty_text() -> None:
    response = client.post("/clean", json={"text": "   ", "mode": "strict"})
    assert response.status_code == 422


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
