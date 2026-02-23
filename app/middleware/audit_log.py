"""ASGI middleware for per-request structured audit logging."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from app.core.observability import get_request_id

logger = logging.getLogger("gramlynx.audit")


class AuditLogMiddleware:
    """Emit one safe structured audit log line per HTTP request."""

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        start = time.perf_counter()
        request_state = scope.setdefault("state", {})

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = (time.perf_counter() - start) * 1000
        payload: dict[str, Any] = {
            "event": "request_audit",
            "request_id": get_request_id(),
            "method": scope.get("method"),
            "path": scope.get("path"),
            "status_code": status_code,
            "duration_ms": round(duration_ms, 3),
        }

        if scope.get("path") == "/clean":
            clean_audit = request_state.get("clean_audit")
            if isinstance(clean_audit, dict):
                payload.update(clean_audit)

        logger.info(json.dumps(payload, ensure_ascii=False))

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app
