"""API endpoints for LLM-powered tutor assistance"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.text import Text, TextSegment
from services.tutor import (
    TutorService,
    TutorServiceError,
    TranslationSuggestion,
    get_tutor_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


class TranslationSuggestionRequest(BaseModel):
    """Client payload for asking the tutor for a translation suggestion."""

    text_id: int = Field(..., description="ID of the text the selection belongs to")
    segment_id: int = Field(..., description="ID of the segment providing context")
    selection: str = Field(..., min_length=1, description="The selected source text")
    translation_draft: Optional[str] = Field(
        None,
        description="Optional student-provided translation to improve",
    )
    language: Optional[str] = Field(
        None, description="ISO code of the source language (defaults to text.language)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional UI metadata (e.g. student level, notes)",
    )


@router.post(
    "/suggest-translation",
    response_model=TranslationSuggestion,
    status_code=status.HTTP_200_OK,
)
async def suggest_translation(
    payload: TranslationSuggestionRequest,
    db: Session = Depends(get_db),
    tutor_service: TutorService = Depends(get_tutor_service),
):
    """
    Request a contextual translation suggestion for a highlighted passage.

    The endpoint retrieves the relevant text + segment for context, then
    delegates to the TutorService which orchestrates the LLM prompt/response.
    """

    if not settings.LLM_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM features are currently disabled",
        )

    # Validate text & segment relationship
    text = db.get(Text, payload.text_id)
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")

    segment = (
        db.query(TextSegment)
        .filter(TextSegment.id == payload.segment_id, TextSegment.text_id == text.id)
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found for text")

    logger.info(
        "Tutor suggestion requested",
        extra={
            "text_id": text.id,
            "segment_id": segment.id,
            "language": payload.language or text.language,
        },
    )

    try:
        suggestion = await tutor_service.suggest_translation(
            text=text,
            segment=segment,
            selection=payload.selection,
            translation_draft=payload.translation_draft,
            language=payload.language or text.language,
            metadata=payload.metadata or {},
        )
    except TutorServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    return suggestion


