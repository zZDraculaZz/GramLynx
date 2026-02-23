"""FastAPI entrypoint."""
from __future__ import annotations

import os

from fastapi import FastAPI

from app.api.routes import router
from app.middleware.max_body_size import MaxBodySizeMiddleware

DEFAULT_MAX_BODY_BYTES = 1_048_576


def _get_max_body_bytes() -> int:
    value = os.getenv("GRAMLYNX_MAX_BODY_BYTES")
    if value is None:
        return DEFAULT_MAX_BODY_BYTES
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_MAX_BODY_BYTES
    return parsed if parsed > 0 else DEFAULT_MAX_BODY_BYTES


app = FastAPI(title="Text Clean Service", version="0.1.0")
app.add_middleware(MaxBodySizeMiddleware, max_body_bytes=_get_max_body_bytes())
app.include_router(router)

if os.getenv("GRAMLYNX_ENABLE_METRICS") == "1":
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
