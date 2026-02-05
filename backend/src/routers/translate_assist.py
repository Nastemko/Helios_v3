"""API endpoints for Translation Assist feature."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from config import settings
from services.translate_assist import (
    TranslateAssistError,
    TranslateAssistService,
    TranslationResult,
    get_translate_assist_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translate-assist", tags=["translate-assist"])


class TranslateRequest(BaseModel):
    """Request payload for translation."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=600,
        description="Greek text to translate (max ~1 paragraph)",
    )
    language: str = Field(
        default="grc",
        description="Source language code (grc for Greek, lat for Latin)",
    )


@router.post(
    "",
    response_model=TranslationResult,
    status_code=status.HTTP_200_OK,
    summary="Translate Greek text",
    description="Submit Ancient Greek text (up to a paragraph) for AI-powered translation suggestions.",
)
async def translate_text(
    payload: TranslateRequest,
    service: TranslateAssistService = Depends(get_translate_assist_service),
):
    """
    Translate a passage of Ancient Greek text.

    Returns a structured translation with:
    - translation: Clear English rendering
    - literal_gloss: Optional word-by-word translation
    - rationale: Explanation of grammar and vocabulary choices
    - confidence: Model's self-assessed confidence (0.0-1.0)
    """
    if not settings.llm.ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Translation features are currently disabled",
        )

    logger.info(
        "Translation assist request",
        extra={
            "text_length": len(payload.text),
            "language": payload.language,
        },
    )

    try:
        result = await service.translate(
            text=payload.text,
            language=payload.language,
        )
    except TranslateAssistError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    return result


@router.get(
    "/status",
    summary="Check translation service status",
    description="Check if the translation service is available and configured.",
)
async def translation_status():
    """Return the current status of the translation service."""
    return {
        "enabled": settings.llm.ENABLED,
        "model": settings.llm.MODEL if settings.llm.ENABLED else None,
        "max_chars": 600,
    }
