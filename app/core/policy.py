"""Policy Engine и конфигурация."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.core.config import load_app_config


@dataclass(frozen=True)
class PolicyConfig:
    """Конфигурация поведения пайплайна."""

    enabled_stages: List[str]
    max_edits_per_sentence: int
    max_edits_total: int
    max_changed_char_ratio: float
    min_confidence_per_edit: float
    min_confidence_overall: float
    allow_punct_stage: bool
    language_gate_thresholds: float
    pz_buffer_chars: int


STRICT_POLICY = PolicyConfig(
    enabled_stages=["s1_normalize", "s2_segment", "s6_guardrails", "s7_assemble"],
    max_edits_per_sentence=1,
    max_edits_total=5,
    max_changed_char_ratio=0.02,
    min_confidence_per_edit=0.99,
    min_confidence_overall=0.99,
    allow_punct_stage=False,
    language_gate_thresholds=0.9,
    pz_buffer_chars=2,
)

SMART_POLICY = PolicyConfig(
    enabled_stages=[
        "s1_normalize",
        "s2_segment",
        "s3_spelling",
        "s4_grammar",
        "s5_punct",
        "s6_guardrails",
        "s7_assemble",
    ],
    max_edits_per_sentence=2,
    max_edits_total=10,
    max_changed_char_ratio=0.1,
    min_confidence_per_edit=0.95,
    min_confidence_overall=0.95,
    allow_punct_stage=True,
    language_gate_thresholds=0.8,
    pz_buffer_chars=1,
)


def _apply_overrides(base: PolicyConfig, mode: str) -> PolicyConfig:
    cfg = load_app_config()
    policy_override = cfg.policies.smart if mode == "smart" else cfg.policies.strict

    return PolicyConfig(
        enabled_stages=policy_override.enabled_stages or list(base.enabled_stages),
        max_edits_per_sentence=base.max_edits_per_sentence,
        max_edits_total=base.max_edits_total,
        max_changed_char_ratio=(
            policy_override.max_changed_char_ratio
            if policy_override.max_changed_char_ratio is not None
            else base.max_changed_char_ratio
        ),
        min_confidence_per_edit=base.min_confidence_per_edit,
        min_confidence_overall=base.min_confidence_overall,
        allow_punct_stage=base.allow_punct_stage,
        language_gate_thresholds=base.language_gate_thresholds,
        pz_buffer_chars=(
            policy_override.pz_buffer_chars
            if policy_override.pz_buffer_chars is not None
            else base.pz_buffer_chars
        ),
    )


def get_policy(mode: str) -> PolicyConfig:
    """Возвращает конфиг политики по режиму."""

    if mode == "smart":
        return _apply_overrides(SMART_POLICY, mode="smart")
    return _apply_overrides(STRICT_POLICY, mode="strict")
