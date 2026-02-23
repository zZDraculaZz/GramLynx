"""Allow/Deny lexicon placeholders."""
from __future__ import annotations

from app.core.config import load_app_config

DEFAULT_ALLOWLIST = {"Python", "FastAPI", "Docker"}
DEFAULT_DENYLIST = {"TODO", "FIXME"}


def get_allowlist() -> set[str]:
    """Return configured allowlist or default one."""

    configured = load_app_config().lexicon.allowlist
    return set(configured) if configured is not None else set(DEFAULT_ALLOWLIST)


def get_denylist() -> set[str]:
    """Return configured denylist or default one."""

    configured = load_app_config().lexicon.denylist
    return set(configured) if configured is not None else set(DEFAULT_DENYLIST)
