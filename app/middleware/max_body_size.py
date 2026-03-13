"""ASGI middleware for limiting incoming HTTP request body size."""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class MaxBodySizeMiddleware:
    """Reject requests with body larger than configured byte limit."""

    def __init__(self, app: Callable[..., Awaitable[Any]], max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max(1, int(max_body_bytes))

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        total = 0

        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break

            body = message.get("body", b"") or b""
            total += len(body)
            if total > self.max_body_bytes:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Payload Too Large"}',
                        "more_body": False,
                    }
                )
                return

            chunks.append(body)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> dict[str, Any]:
            nonlocal index
            if index < len(chunks):
                chunk = chunks[index]
                index += 1
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": index < len(chunks),
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)
