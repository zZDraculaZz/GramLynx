"""Фабрика сборки пайплайна по политике."""
from __future__ import annotations

from typing import List

from app.core.policy import PolicyConfig
from app.core.stages.base import Stage
from app.core.stages.registry import get_stage_class

from app.core.stages import builtins  # noqa: F401
from app.core.stages import custom_example  # noqa: F401


def build_pipeline(policy: PolicyConfig) -> List[Stage]:
    """Собирает список стадий по enabled_stages."""

    stages: List[Stage] = []
    for stage_name in policy.enabled_stages:
        stage_cls = get_stage_class(stage_name)
        stages.append(stage_cls())
    return stages
