from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_has_smart_baseline_profile_service() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose.get("services", {})

    assert "app" in services
    assert "app-smart-baseline" in services

    baseline = services["app-smart-baseline"]
    assert baseline.get("profiles") == ["smart-baseline"]
    environment = baseline.get("environment", [])
    assert "GRAMLYNX_CONFIG_YAML=/app/config.smart_baseline_staging.yml" in environment
