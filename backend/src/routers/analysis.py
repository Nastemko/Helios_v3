"""API endpoints for word analysis"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from src.services.morphology import MorphologyService, get_morphology_service

router = APIRouter(prefix="/api/analyze", tags=["analysis"])


class WordAnalysisRequest(BaseModel):
    """Request model for word analysis"""
    word: str
    language: str  # 'grc' or 'lat'
    context: Optional[str] = None


class WordAnalysisResponse(BaseModel):
    """Response model for word analysis"""
    word: str
    language: str
    lemma: str
    pos: str
    morphology: dict
    definitions: list[str]
    lexicon_url: str
    perseus_url: Optional[str] = None


@router.post("/word", response_model=WordAnalysisResponse)
async def analyze_word(
    request: WordAnalysisRequest,
    morphology_service: MorphologyService = Depends(get_morphology_service)
):
    """
    Analyze a Greek or Latin word
    
    Returns morphological information, definitions, and lexicon links.
    
    Example request:
    ```json
    {
        "word": "μῆνιν",
        "language": "grc",
        "context": "μῆνιν ἄειδε θεὰ"
    }
    ```
    """
    result = await morphology_service.analyze_word(
        word=request.word,
        language=request.language,
        context=request.context
    )
    
    return WordAnalysisResponse(**result)


@router.get("/lexicon-url")
async def get_lexicon_url(
    lemma: str,
    language: str,
    morphology_service: MorphologyService = Depends(get_morphology_service)
):
    """
    Get lexicon URL for a lemma
    
    Useful for generating direct links to online lexicons.
    """
    url = morphology_service.get_lexicon_url(lemma, language)
    return {"lemma": lemma, "language": language, "url": url}

