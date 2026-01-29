"""API schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CleanRequest(BaseModel):
    """Request payload for text cleaning."""

    text: str = Field(..., min_length=1, max_length=20000)
    mode: Literal["strict", "smart"] = "strict"
    options: Optional[dict] = None


class CleanResponse(BaseModel):
    """Response payload for text cleaning."""

    clean_text: str
