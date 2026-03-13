"""Application configuration loading from YAML with strict validation."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MODEL_CONFIG = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ConfigError(RuntimeError):
    """Raised when external YAML config is invalid."""


class LimitsConfig(BaseModel):
    model_config = MODEL_CONFIG

    max_body_bytes: int = Field(default=1_048_576, gt=0)
    max_text_chars: int = Field(default=20_000, gt=0)


class PolicyOverrides(BaseModel):
    model_config = MODEL_CONFIG

    enabled_stages: list[str] | None = None
    max_changed_char_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    pz_buffer_chars: int | None = Field(default=None, ge=0)


class PoliciesConfig(BaseModel):
    model_config = MODEL_CONFIG

    strict: PolicyOverrides = Field(default_factory=PolicyOverrides)
    smart: PolicyOverrides = Field(default_factory=PolicyOverrides)


class LexiconConfig(BaseModel):
    model_config = MODEL_CONFIG

    allowlist: list[str] | None = None
    denylist: list[str] | None = None




class RulepackPunctuationConfig(BaseModel):
    model_config = MODEL_CONFIG

    fix_space_before: bool = True
    fix_space_after: bool = True


class RulepackSafeNormalizeConfig(BaseModel):
    model_config = MODEL_CONFIG

    collapse_spaces: bool = True
    trim_line_edges: bool = True
    collapse_blank_lines: bool = True


class RulepackPunctuationSpacingRuConfig(BaseModel):
    model_config = MODEL_CONFIG

    fix_space_before: bool = True
    fix_space_after: bool = True


class RulepackConfig(BaseModel):
    model_config = MODEL_CONFIG

    typo_map_strict: dict[str, str] = Field(default_factory=dict)
    typo_map_smart: dict[str, str] = Field(default_factory=dict)
    typo_map_strict_ru: dict[str, str] = Field(default_factory=dict)
    typo_map_smart_ru: dict[str, str] = Field(default_factory=dict)
    no_touch_strict_ru: list[str] = Field(default_factory=list)
    no_touch_smart_ru: list[str] = Field(default_factory=list)
    no_touch_prefixes_ru: list[str] = Field(default_factory=list)
    typo_min_token_len: int = Field(default=4, ge=1)
    enable_morph_safety_ru: bool = False
    enable_candidate_generation_ru: bool = False
    candidate_shadow_mode_ru: bool = False
    candidate_backend: str = "none"
    max_candidates_ru: int = Field(default=3, ge=1, le=10)
    max_edit_distance_ru: int = Field(default=1, ge=1, le=2)
    dictionary_source_ru: str = ""
    safe_normalize: RulepackSafeNormalizeConfig = Field(default_factory=RulepackSafeNormalizeConfig)
    punctuation: RulepackPunctuationConfig = Field(default_factory=RulepackPunctuationConfig)
    punctuation_spacing_ru: RulepackPunctuationSpacingRuConfig = Field(
        default_factory=RulepackPunctuationSpacingRuConfig
    )

    def typo_map_for_mode(self, mode: str) -> dict[str, str]:
        if mode == "smart":
            return self.typo_map_smart_ru or self.typo_map_smart
        return self.typo_map_strict_ru or self.typo_map_strict

    def no_touch_for_mode(self, mode: str) -> set[str]:
        if mode == "smart":
            base = self.no_touch_smart_ru or self.no_touch_strict_ru
        else:
            base = self.no_touch_strict_ru
        return {token for token in base if token}

    def no_touch_prefixes_for_mode(self, mode: str) -> tuple[str, ...]:
        _ = mode
        return tuple(prefix for prefix in self.no_touch_prefixes_ru if prefix)

    def punctuation_for_mode(self) -> RulepackPunctuationSpacingRuConfig:
        if (
            self.punctuation_spacing_ru.fix_space_before is not True
            or self.punctuation_spacing_ru.fix_space_after is not True
        ):
            return self.punctuation_spacing_ru
        return RulepackPunctuationSpacingRuConfig(
            fix_space_before=self.punctuation.fix_space_before,
            fix_space_after=self.punctuation.fix_space_after,
        )


class AppConfig(BaseModel):
    model_config = MODEL_CONFIG

    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    lexicon: LexiconConfig = Field(default_factory=LexiconConfig)
    rulepack: RulepackConfig = Field(default_factory=RulepackConfig)


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
        first = exc.errors()[0]
        err_type = first.get("type", "validation_error")
        loc = ".".join(str(part) for part in first.get("loc", [])) or "root"
        raise ConfigError(f"Invalid config YAML: validation_failed at {loc} ({err_type})") from exc

    _validate_stages(cfg)
    return cfg


def reset_app_config_cache() -> None:
    """Reset config cache (test helper)."""

    load_app_config.cache_clear()
