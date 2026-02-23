"""FastAPI entrypoint."""
from __future__ import annotations

import os

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Text Clean Service", version="0.1.0")
app.include_router(router)

if os.getenv("GRAMLYNX_ENABLE_METRICS") == "1":
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
