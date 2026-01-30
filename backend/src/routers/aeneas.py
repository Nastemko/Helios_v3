"""API endpoints for Ithaca/Aeneas model via IthacaService

This router replaces the deprecated direct Aeneas usage and proxies requests
to the `IthacaService` implementation which supports both Greek (Ithaca) and
Latin (Aeneas) models.
"""

from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from services.ithaca_service.ithaca_service import IthacaService, get_ithaca_service

router = APIRouter(prefix="/api/aeneas", tags=["aeneas"])


class RestoreRequest(BaseModel):
    """Request model for text restoration"""

    text: str = Field(
        ...,
        min_length=50,
        max_length=750,
        description="Text with # marking missing characters",
    )
    language: Literal["greek", "latin"] = Field(
        ..., description="Language: 'greek' or 'latin'"
    )
    beam_width: int = Field(100, ge=1, le=200, description="Beam width for search")
    temperature: float = Field(1.0, ge=0.1, le=2.0, description="Sampling temperature")
    max_len: int = Field(15, ge=1, le=30, description="Max restoration length")

    @field_validator("text", mode="after")
    @classmethod
    def text_cleanup(cls, value: str):
        return value.replace("-", "?")


class AttributeRequest(BaseModel):
    """Request model for text attribution"""

    text: str = Field(
        ..., min_length=50, max_length=750, description="Text to attribute"
    )
    language: Literal["greek", "latin"] = Field(
        ..., description="Language: 'greek' or 'latin'"
    )


class ContextualizeRequest(BaseModel):
    """Request model for text contextualization"""

    text: str = Field(
        ..., min_length=50, max_length=750, description="Text to contextualize"
    )
    language: Literal["greek", "latin"] = Field(
        ..., description="Language: 'greek' or 'latin'"
    )


@router.get("/status")
async def get_status(service: Optional[IthacaService] = Depends(get_ithaca_service)):
    """
    Get Ithaca/Aeneas service status

    Returns information about which models are loaded and available.
    """
    if service is None:
        return {"available": False, "message": "Ithaca service not initialized"}

    status = service.get_status()
    overall_available = status.get("greek", {}).get("available", False) or status.get(
        "latin", {}
    ).get("available", False)

    return {
        "available": overall_available,
        "models": {
            "greek": status.get("greek", {}).get("available", False),
            "latin": status.get("latin", {}).get("available", False),
        },
        "message": "Ithaca/Aeneas service ready"
        if overall_available
        else "No models loaded",
        "raw": status,
    }


@router.post("/restore")
async def restore_text(
    request: RestoreRequest,
    service: Optional[IthacaService] = Depends(get_ithaca_service),
):
    """
    Restore damaged text

    Use # to mark missing characters in the input text.
    The model will suggest possible restorations.

    Example:
    ```json
    {
        "text": "μῆνιν ἄ#ιδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        "language": "greek"
    }
    ```

    Note: Text must be between 50 and 750 characters.
    """
    if service is None or not service.is_available(request.language):
        raise HTTPException(
            status_code=503,
            detail=f"Ithaca/Aeneas model not available for language: {request.language}",
        )

    result = service.restore(
        text=request.text,
        language=request.language,
        beam_width=request.beam_width,
        temperature=request.temperature,
        max_restoration_len=request.max_len,
    )

    # Convert dataclass result to serializable dict
    try:
        return asdict(result)
    except Exception:
        # Fallback: return a minimal error response
        raise HTTPException(
            status_code=500, detail="Failed to serialize restoration result"
        )


@router.post("/attribute")
async def attribute_text(
    request: AttributeRequest,
    service: Optional[IthacaService] = Depends(get_ithaca_service),
):
    """
    Predict geographical origin and date of text

    Example:
    ```json
    {
        "text": "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        "language": "greek"
    }
    ```

    Returns predictions for:
    - Geographical location
    - Date range
    """
    if service is None or not service.is_available(request.language):
        raise HTTPException(
            status_code=503,
            detail=f"Ithaca/Aeneas model not available for language: {request.language}",
        )

    result = service.attribute(text=request.text, language=request.language)

    try:
        return asdict(result)
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to serialize attribution result"
        )


@router.post("/contextualize")
async def contextualize_text(
    request: ContextualizeRequest,
    service: Optional[IthacaService] = Depends(get_ithaca_service),
):
    """
    Find similar inscriptions and contextual parallels

    Example:
    ```json
    {
        "text": "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        "language": "greek"
    }
    ```

    Returns:
    - Similar inscriptions from the database
    - Relevance scores
    - Metadata about parallels
    """
    if service is None or not service.is_available(request.language):
        raise HTTPException(
            status_code=503,
            detail=f"Ithaca/Aeneas model not available for language: {request.language}",
        )

    result = service.contextualize(text=request.text, language=request.language)

    try:
        return asdict(result)
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to serialize contextualization result"
        )
