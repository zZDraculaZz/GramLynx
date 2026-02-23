"""Application configuration loading from YAML with strict validation."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfigError(RuntimeError):
    """Raised when external YAML config is invalid."""


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_body_bytes: int = Field(default=1_048_576, gt=0)
    max_text_chars: int = Field(default=20_000, gt=0)


class PolicyOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled_stages: list[str] | None = None
    max_changed_char_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    pz_buffer_chars: int | None = Field(default=None, ge=0)


class PoliciesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strict: PolicyOverrides = Field(default_factory=PolicyOverrides)
    smart: PolicyOverrides = Field(default_factory=PolicyOverrides)


class LexiconConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowlist: list[str] | None = None
    denylist: list[str] | None = None


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    lexicon: LexiconConfig = Field(default_factory=LexiconConfig)


_ALLOWED_STAGES = {
    "s1_normalize",
    "s2_segment",
    "s3_spelling",
    "s4_grammar",
    "s5_punct",
    "s6_guardrails",
    "s7_assemble",
    "custom_example",
}


def _validate_stages(config: AppConfig) -> None:
    for mode in ("strict", "smart"):
        policy = getattr(config.policies, mode)
        if policy.enabled_stages is None:
            continue
        unknown = [name for name in policy.enabled_stages if name not in _ALLOWED_STAGES]
        if unknown:
            raise ConfigError(f"Invalid config YAML: unknown stage(s) for {mode}: {', '.join(unknown)}")


def _read_yaml(path: str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists() or not config_path.is_file():
        raise ConfigError(f"Invalid config YAML: file not found: {path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid config YAML: {exc.__class__.__name__}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("Invalid config YAML: root must be a mapping")
    return raw


@lru_cache(maxsize=1)
def load_app_config() -> AppConfig:
    config_path = os.getenv("GRAMLYNX_CONFIG_YAML")
    if not config_path:
        return AppConfig()

    raw = _read_yaml(config_path)
    try:
        cfg = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config YAML: {exc.errors()[0]['msg']}") from exc

    _validate_stages(cfg)
    return cfg


def reset_app_config_cache() -> None:
    """Reset config cache (test helper)."""

    load_app_config.cache_clear()
