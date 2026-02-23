"""FastAPI entrypoint."""
from __future__ import annotations

import os

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import ConfigError, load_app_config
from app.core.observability import log_event
from app.middleware.max_body_size import MaxBodySizeMiddleware
from app.middleware.request_id import RequestIDMiddleware

DEFAULT_MAX_BODY_BYTES = 1_048_576


def _get_max_body_bytes() -> int:
    raw = os.getenv("GRAMLYNX_MAX_BODY_BYTES")
    if raw is not None:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    cfg = load_app_config()
    return cfg.limits.max_body_bytes or DEFAULT_MAX_BODY_BYTES


try:
    _APP_CONFIG = load_app_config()
except ConfigError as exc:
    log_event(event="startup_failed", reason=str(exc))
    raise RuntimeError(str(exc)) from exc

app = FastAPI(title="Text Clean Service", version="0.1.0")
app.add_middleware(MaxBodySizeMiddleware, max_body_bytes=_get_max_body_bytes())
app.add_middleware(RequestIDMiddleware)
app.include_router(router)

if os.getenv("GRAMLYNX_ENABLE_METRICS") == "1":
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
