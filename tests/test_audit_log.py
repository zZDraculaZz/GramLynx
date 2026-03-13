"""Tests for safe per-request audit logging."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_clean_audit_log_has_request_id_and_no_text_leak(caplog) -> None:
    caplog.set_level("INFO", logger="gramlynx.audit")
    source_text = "Привет мир"

    response = client.post(
        "/clean",
        json={"text": source_text, "mode": "strict"},
        headers={"X-Request-ID": "abc"},
    )

    assert response.status_code == 200

    audit_records = [r for r in caplog.records if r.name == "gramlynx.audit"]
    assert audit_records

    payload = json.loads(audit_records[-1].message)
    assert payload["request_id"] == "abc"

    rendered = audit_records[-1].message
    assert source_text not in rendered
    assert '"text"' not in rendered
    assert '"clean_text"' not in rendered

    assert payload["path"] == "/clean"
    assert "input_len_chars" in payload
    assert "output_len_chars" in payload
    assert "changed_ratio" in payload
    assert "confidence" in payload
    assert "rollback_applied" in payload
    assert "pz_spans_count" in payload
