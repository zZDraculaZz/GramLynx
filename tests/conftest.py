"""Конфигурация pytest."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Dict, Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_cases() -> List[Dict[str, Any]]:
    """Загружает тест-кейсы из YAML."""

    cases_path = ROOT / "tests" / "cases.yaml"
    with cases_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or []
    return list(data)
