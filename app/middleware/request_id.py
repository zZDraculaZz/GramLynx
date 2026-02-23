"""ASGI middleware to propagate/generate request ids."""
from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Any, Awaitable, Callable

from starlette.datastructures import MutableHeaders

from app.core.observability import set_request_id


class RequestIDMiddleware:
    """Attach X-Request-ID to request context and response headers."""

    header_name = b"x-request-id"

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._extract_request_id(scope) or str(uuid.uuid4())
        token = set_request_id(request_id)

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            with suppress(Exception):
                set_request_id(None, token=token)

    def _extract_request_id(self, scope: dict[str, Any]) -> str | None:
        for key, value in scope.get("headers", []):
            if key.lower() == self.header_name:
                text = value.decode("utf-8", errors="ignore").strip()
                if text:
                    return text
        return None
