"""API endpoints for Aeneas AI model"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from services.aeneas_service import AeneasService, get_aeneas_service

router = APIRouter(prefix="/api/aeneas", tags=["aeneas"])


class RestoreRequest(BaseModel):
    """Request model for text restoration"""
    text: str = Field(..., min_length=50, max_length=750, description="Text with # marking missing characters")
    language: str = Field(..., description="Language: 'greek' or 'latin'")
    beam_width: int = Field(100, ge=1, le=200, description="Beam width for search")
    temperature: float = Field(1.0, ge=0.1, le=2.0, description="Sampling temperature")
    max_len: int = Field(15, ge=1, le=30, description="Max restoration length")


class AttributeRequest(BaseModel):
    """Request model for text attribution"""
    text: str = Field(..., min_length=50, max_length=750, description="Text to attribute")
    language: str = Field(..., description="Language: 'greek' or 'latin'")


class ContextualizeRequest(BaseModel):
    """Request model for text contextualization"""
    text: str = Field(..., min_length=50, max_length=750, description="Text to contextualize")
    language: str = Field(..., description="Language: 'greek' or 'latin'")


@router.get("/status")
async def get_status(service: Optional[AeneasService] = Depends(get_aeneas_service)):
    """
    Get Aeneas service status
    
    Returns information about which models are loaded and available.
    """
    if service is None:
        return {
            "available": False,
            "message": "Aeneas service not initialized"
        }
    
    return {
        "available": service.is_available(),
        "models": {
            "greek": service.is_available('greek'),
            "latin": service.is_available('latin')
        },
        "message": "Aeneas service ready" if service.is_available() else "No models loaded"
    }


@router.post("/restore")
async def restore_text(
    request: RestoreRequest,
    service: Optional[AeneasService] = Depends(get_aeneas_service)
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
            detail=f"Aeneas model not available for language: {request.language}"
        )
    
    result = await service.restore_text(
        text=request.text,
        language=request.language,
        beam_width=request.beam_width,
        temperature=request.temperature,
        max_len=request.max_len
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/attribute")
async def attribute_text(
    request: AttributeRequest,
    service: Optional[AeneasService] = Depends(get_aeneas_service)
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
            detail=f"Aeneas model not available for language: {request.language}"
        )
    
    result = await service.attribute_text(
        text=request.text,
        language=request.language
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/contextualize")
async def contextualize_text(
    request: ContextualizeRequest,
    service: Optional[AeneasService] = Depends(get_aeneas_service)
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
            detail=f"Aeneas model not available for language: {request.language}"
        )
    
    result = await service.contextualize_text(
        text=request.text,
        language=request.language
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

