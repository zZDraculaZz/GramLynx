"""Tests for YAML-based application configuration."""
from __future__ import annotations

import importlib

import pytest

from app.core.config import load_app_config, reset_app_config_cache
from app.core.policy import get_policy
from app.core.protected_zones.lexicon import get_allowlist, get_denylist


def _reset(monkeypatch) -> None:
    monkeypatch.delenv("GRAMLYNX_CONFIG_YAML", raising=False)
    reset_app_config_cache()


def test_valid_yaml_applies_overrides(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "valid.yml"
    config_file.write_text(
        """
limits:
  max_body_bytes: 2048
  max_text_chars: 123
policies:
  strict:
    max_changed_char_ratio: 0.03
    pz_buffer_chars: 5
    enabled_stages: [s1_normalize, s2_segment, s6_guardrails, s7_assemble]
lexicon:
  allowlist: [One, Two]
  denylist: [Bad]
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    reset_app_config_cache()

    import app.main as app_main

    importlib.reload(app_main)

    cfg = load_app_config()
    assert cfg.limits.max_body_bytes == 2048
    assert cfg.limits.max_text_chars == 123

    strict = get_policy("strict")
    assert strict.max_changed_char_ratio == 0.03
    assert strict.pz_buffer_chars == 5
    assert strict.enabled_stages == ["s1_normalize", "s2_segment", "s6_guardrails", "s7_assemble"]

    assert get_allowlist() == {"One", "Two"}
    assert get_denylist() == {"Bad"}


def test_invalid_yaml_fails_closed_on_startup(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "invalid.yml"
    config_file.write_text(
        """
limits:
  max_body_bytes: -1
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAMLYNX_CONFIG_YAML", str(config_file))
    reset_app_config_cache()

    with pytest.raises(RuntimeError, match="Invalid config YAML"):
        import app.main as app_main

        importlib.reload(app_main)


def test_defaults_used_when_env_not_set(monkeypatch) -> None:
    _reset(monkeypatch)

    cfg = load_app_config()
    assert cfg.limits.max_body_bytes == 1_048_576
    assert cfg.limits.max_text_chars == 20_000

    strict = get_policy("strict")
    assert strict.max_changed_char_ratio == 0.02
    assert strict.pz_buffer_chars == 2

    assert get_allowlist() == {"Python", "FastAPI", "Docker"}
    assert get_denylist() == {"TODO", "FIXME"}
