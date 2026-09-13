"""API endpoints for word analysis"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services.morphology import MorphologyService, get_morphology_service

router = APIRouter(prefix="/api/analyze", tags=["analysis"])

# Segments are sentence/line sized; anything far beyond that would be fed
# whole to Stanza on the threadpool, so bound the inputs at the API edge.
MAX_WORD_LENGTH = 100
MAX_CONTEXT_LENGTH = 5000


class WordAnalysisRequest(BaseModel):
    """Request model for word analysis"""

    word: str = Field(max_length=MAX_WORD_LENGTH)
    language: str = Field(max_length=10)  # 'grc' or 'lat'
    context: Optional[str] = Field(default=None, max_length=MAX_CONTEXT_LENGTH)
    word_occurrence: int = Field(default=0, ge=0)  # 0-based clicked occurrence


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
    morphology_service: MorphologyService = Depends(get_morphology_service),
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
        context=request.context,
        word_occurrence=request.word_occurrence,
    )

    return WordAnalysisResponse(**result)
