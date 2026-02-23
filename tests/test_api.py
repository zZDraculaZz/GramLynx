"""API tests."""
from __future__ import annotations

import uuid

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


def test_request_id_echo_from_client_header() -> None:
    response = client.post(
        "/clean",
        json={"text": "Привет", "mode": "strict"},
        headers={"X-Request-ID": "abc"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "abc"


def test_request_id_generated_when_missing() -> None:
    response = client.post("/clean", json={"text": "Привет", "mode": "strict"})
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    uuid.UUID(request_id)
