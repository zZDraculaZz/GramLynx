from __future__ import annotations

import importlib.util


MISSING_BACKEND_HINT = (
    "encoder_ranker backend unavailable: install optional research extras with "
    "`pip install -e '.[research-encoder]'` (or install torch + transformers manually)."
)


def missing_encoder_backend_packages() -> tuple[str, ...]:
    missing: list[str] = []
    if importlib.util.find_spec("torch") is None:
        missing.append("torch")
    if importlib.util.find_spec("transformers") is None:
        missing.append("transformers")
    return tuple(missing)


def encoder_backend_ready() -> bool:
    return not missing_encoder_backend_packages()


def encoder_backend_blocker_message() -> str:
    missing = missing_encoder_backend_packages()
    if not missing:
        return ""
    return f"{MISSING_BACKEND_HINT} Missing: {', '.join(missing)}"
