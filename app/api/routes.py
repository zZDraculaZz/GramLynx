"""API routes."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.api.schemas import CleanRequest, CleanResponse
from app.core.config import load_app_config
from app.core.orchestrator import Orchestrator
from app.core.observability import get_correlation_id

router = APIRouter()


@router.post("/clean", response_model=CleanResponse)
async def clean_text(
    payload: CleanRequest,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> CleanResponse:
    """Clean input text and return safe output."""
    correlation_id = get_correlation_id(x_correlation_id)
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="Text cannot be empty")

    max_text_chars = load_app_config().limits.max_text_chars
    if len(payload.text) > max_text_chars:
        raise HTTPException(status_code=422, detail="Text too long")
    orchestrator = Orchestrator(correlation_id=correlation_id)
    clean = orchestrator.run(text=payload.text, mode=payload.mode)
    return CleanResponse(clean_text=clean)


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe endpoint."""

    return {"status": "ok"}
