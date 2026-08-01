"""API endpoints for browsing and querying PHI inscriptions"""

from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.inscription import Inscription, InscriptionSegment
from models.user import User
from services.ithaca_service.ithaca_service import (
    get_ithaca_service,
    initialize_all_models,
)

router = APIRouter(prefix="/api/inscriptions", tags=["inscriptions"])

# Type alias for language
Language = Literal["greek", "latin"]


# Response models
class TextResponse(BaseModel):
    """Text metadata response"""

    id: int
    phi_id: Optional[int] = None
    title: str
    text: str  # Full inscription text
    region_main: Optional[str] = None
    region_sub: Optional[str] = None
    date_str: Optional[str] = None
    date_min: Optional[int] = None
    date_max: Optional[int] = None
    date_circa: Optional[bool] = None
    metadata_raw: Optional[str] = None

    model_config = {"from_attributes": True}


class TextListItem(BaseModel):
    """Text list item (lighter version)"""

    id: int
    phi_id: Optional[int] = None
    title: str
    text_preview: str  # First ~100 chars
    region_main: Optional[str] = None
    region_sub: Optional[str] = None
    date_str: Optional[str] = None
    date_min: Optional[int] = None
    date_max: Optional[int] = None

    model_config = {"from_attributes": True}


class RegionCount(BaseModel):
    """Region with inscription count"""

    region: str
    region_id: Optional[str] = None
    count: int


class TextStats(BaseModel):
    """Statistics about the inscription corpus"""

    total_inscriptions: int
    inscriptions_with_dates: int
    regions_count: int
    date_range: dict


def _get_full_text(db: Session, inscription_id: int) -> str:
    """Get full inscription text by joining segments"""
    segments = db.scalars(
        select(InscriptionSegment)
        .filter(InscriptionSegment.inscription_id == inscription_id)
        .order_by(InscriptionSegment.sequence)
    ).all()

    return ". ".join(str(seg.content) for seg in segments if str(seg.content))


@router.get("/", response_model=List[TextListItem])
async def list_inscriptions(
    search: Optional[str] = Query(None, description="Search in text content"),
    region_main: Optional[str] = Query(None, description="Filter by main region"),
    region_sub: Optional[str] = Query(None, description="Filter by sub-region"),
    date_min: Optional[int] = Query(None, description="Minimum date (negative = BC)"),
    date_max: Optional[int] = Query(None, description="Maximum date (negative = BC)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of records"),
    db: Session = Depends(get_db),
):
    """
    List and search inscriptions with filtering options.

    Date format: negative values are BC (e.g., -350 = 350 BC), positive are AD.
    """
    # Base query - only inscriptions
    query = select(Inscription)

    # Search in inscription content
    if search:
        # Get inscriptions that have matching segments
        search_pattern = f"%{search}%"
        matching_inscription_ids = db.scalars(
            select(InscriptionSegment.inscription_id)
            .filter(InscriptionSegment.content.ilike(search_pattern))
            .distinct()
        ).all()
        query = query.filter(Inscription.id.in_(matching_inscription_ids))

    # Region filters - use extracted columns for better performance
    if region_main:
        query = query.filter(Inscription.region_main == region_main)

    if region_sub:
        query = query.filter(Inscription.region_sub == region_sub)

    # Add date filtering to query using extracted columns
    if date_min is not None:
        query = query.filter(Inscription.date_max >= date_min)
    if date_max is not None:
        query = query.filter(Inscription.date_min <= date_max)

    # Apply pagination after all filters
    inscriptions = db.scalars(
        query.order_by(Inscription.id).offset(skip).limit(limit)
    ).all()

    # Build response with inscription previews
    results = []
    for inscription in inscriptions:
        # Get inscription preview from first segment
        first_segment_content = db.scalar(
            select(InscriptionSegment.content)
            .filter(InscriptionSegment.inscription_id == inscription.id)
            .order_by(InscriptionSegment.sequence)
            .limit(1)
        )

        if first_segment_content and len(first_segment_content) > 150:
            first_segment_content = first_segment_content[:150] + "..."

        results.append(
            TextListItem(
                id=inscription.id,
                phi_id=inscription.phi_id,
                title=inscription.title,
                text_preview=first_segment_content or "",
                region_main=inscription.region_main,
                region_sub=inscription.region_sub,
                date_str=inscription.date_str,
                date_min=inscription.date_min,
                date_max=inscription.date_max,
            )
        )
    return results


@router.get("/regions", response_model=List[RegionCount])
async def list_regions(
    level: str = Query("main", description="Region level: 'main' or 'sub'"),
    db: Session = Depends(get_db),
):
    """
    Get list of regions with inscription counts.

    Use level='main' for top-level regions (e.g., 'Attica (IG I-III)'),
    or level='sub' for sub-regions (e.g., 'Athens: Agora').
    """
    # PHI records carry no region_main_id/region_sub_id — the region name is the
    # only identifier in the source data, so region_id is always None. The
    # previous JSONB cast queried keys that never existed and returned NULL.
    region_column = (
        Inscription.region_main if level == "main" else Inscription.region_sub
    )

    query = (
        select(
            region_column.label("region"),
            func.count().label("count"),
        )
        .filter(region_column.isnot(None))
        .group_by(region_column)
        .order_by(func.count().desc())
    )

    results = db.execute(query).all()

    return [
        RegionCount(
            region=row.region,
            region_id=None,
            count=row.count,
        )
        for row in results
    ]


@router.get("/stats", response_model=TextStats)
async def get_inscription_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the inscription corpus.
    """
    stats_query = select(
        func.count().label("total_inscriptions"),
        func.coalesce(
            func.sum(
                case(
                    (
                        (
                            Inscription.date_min.isnot(None)
                            | Inscription.date_max.isnot(None)
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("inscriptions_with_dates"),
        func.count(func.distinct(Inscription.region_main)).label("regions_count"),
        func.min(Inscription.date_min).label("earliest_date"),
        func.max(Inscription.date_max).label("latest_date"),
    )

    result = db.execute(stats_query).first()

    if not result:
        return TextStats(
            total_inscriptions=0,
            inscriptions_with_dates=0,
            regions_count=0,
            date_range={"earliest": None, "latest": None},
        )

    return TextStats(
        total_inscriptions=result.total_inscriptions,
        inscriptions_with_dates=result.inscriptions_with_dates,
        regions_count=result.regions_count,
        date_range={
            "earliest": result.earliest_date,
            "latest": result.latest_date,
        },
    )


@router.get("/{text_id}", response_model=TextResponse)
async def get_inscription(
    text_id: Annotated[int, Path()], db: Session = Depends(get_db)
):
    """
    Get a specific inscription by its text ID.
    """
    inscription = db.query(Inscription).filter(Inscription.id == text_id).scalar()

    if not inscription:
        raise HTTPException(status_code=404, detail=f"Text not found: {text_id}")

    full_text = _get_full_text(db, inscription.id)
    meta = inscription.metadata_raw or {}

    return TextResponse(
        id=inscription.id,
        phi_id=inscription.phi_id,
        title=inscription.title,
        text=full_text,
        region_main=inscription.region_main,
        region_sub=inscription.region_sub,
        date_str=inscription.date_str,
        date_min=inscription.date_min,
        date_max=inscription.date_max,
        date_circa=inscription.date_circa,
        metadata_raw=meta or None,
    )


# ============================================================================
# ITHACA MODEL ENDPOINTS - Support both Greek and Latin
# ============================================================================


class RestoreRequest(BaseModel):
    """Request for text restoration"""

    text: str
    language: Language = "greek"
    temperature: float = 1.0
    beam_width: int = 100
    max_restoration_len: int = 15

    @field_validator("text", mode="after")
    @classmethod
    def text_cleanup(cls, value: str):
        return value.replace("-", "?")


class RestorationCandidate(BaseModel):
    """A single restoration candidate"""

    text: str
    restored_indices: List[int]
    score: float


class RestoreResponse(BaseModel):
    """Response from restoration model"""

    input_text: str
    language: str
    top_prediction: str
    missing_indices: List[int]
    predictions: List[RestorationCandidate]
    prediction_saliency: List[dict]
    available: bool
    message: Optional[str] = None


class AttributeRequest(BaseModel):
    """Request for attribution (date + location)"""

    text: str
    language: Language = "greek"


class LocationPrediction(BaseModel):
    """A location prediction"""

    location_id: int
    name: str
    score: float


class AttributeResponse(BaseModel):
    """Response from attribution model"""

    input_text: str
    language: str
    locations: List[LocationPrediction]
    year_scores: List[float]  # 160 values for -800 to +800
    predicted_date_range: dict  # {min, max, confidence}
    date_saliency: List[float]
    location_saliency: List[float]
    available: bool
    message: Optional[str] = None


class ContextualizeRequest(BaseModel):
    """Request for finding similar inscriptions"""

    text: str
    language: Language = "greek"
    top_k: int = 20


class SimilarText(BaseModel):
    """A similar inscription"""

    id: str  # PHI ID as string
    ids_alt: Optional[dict] = None
    text: str
    location_id: Optional[int] = None
    date_min: Optional[int] = None
    date_max: Optional[int] = None
    score: float
    partner_link: Optional[str] = None


class ContextualizeResponse(BaseModel):
    """Response with similar inscriptions"""

    similar: List[SimilarText]
    language: str
    available: bool
    message: Optional[str] = None


@router.post("/restore", response_model=RestoreResponse)
async def restore_inscription(
    request: RestoreRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Restore missing characters in an inscription.

    Use '?' for single missing characters and '#' for unknown-length gaps.

    Args:
        text: The inscription text with missing characters
        language: 'greek' or 'latin' (default: greek)
        temperature: Sampling temperature (default: 1.0)
        beam_width: Number of candidates to consider (default: 100)
        max_restoration_len: Max length for unknown-length gaps (default: 15)

    Example Greek: "εδοξεν τηι βουληι και τωι δημωι # αθηναιων"
    Example Latin: "imp caesar divi # f augustus"
    """
    service = get_ithaca_service()

    if not service.is_available(request.language):
        return RestoreResponse(
            input_text=request.text,
            language=request.language,
            top_prediction=request.text,
            missing_indices=[],
            predictions=[],
            prediction_saliency=[],
            available=False,
            message=f"{request.language.title()} model not loaded. Check /api/inscriptions/model/status",
        )

    result = service.restore(
        text=request.text,
        language=request.language,
        beam_width=request.beam_width,
        temperature=request.temperature,
        max_restoration_len=request.max_restoration_len,
    )

    return RestoreResponse(
        input_text=result.input_text,
        language=request.language,
        top_prediction=result.top_prediction,
        missing_indices=result.missing_indices,
        predictions=[
            RestorationCandidate(
                text=p.text, restored_indices=p.restored_indices, score=p.score
            )
            for p in result.predictions
        ],
        prediction_saliency=result.prediction_saliency,
        available=True,
    )


@router.post("/attribute", response_model=AttributeResponse)
async def attribute_inscription(
    request: AttributeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Predict the date and geographic origin of an inscription.

    Args:
        text: The inscription text
        language: 'greek' or 'latin' (default: greek)

    Returns:
    - locations: Top predicted locations with confidence scores
    - year_scores: Probability distribution over years -800 to +800 (10-year intervals)
    - predicted_date_range: Most likely date range
    - saliency maps: Which characters influenced the predictions
    """
    service = get_ithaca_service()

    if not service.is_available(request.language):
        return AttributeResponse(
            input_text=request.text,
            language=request.language,
            locations=[],
            year_scores=[0.0] * 160,
            predicted_date_range={"min": None, "max": None, "confidence": 0.0},
            date_saliency=[],
            location_saliency=[],
            available=False,
            message=f"{request.language.title()} model not loaded. Check /api/inscriptions/model/status",
        )

    result = service.attribute(request.text, language=request.language)

    return AttributeResponse(
        input_text=result.input_text,
        language=request.language,
        locations=[
            LocationPrediction(
                location_id=loc.location_id, name=loc.name, score=loc.score
            )
            for loc in result.locations
        ],
        year_scores=result.year_scores,
        predicted_date_range=result.predicted_date_range,
        date_saliency=result.date_saliency,
        location_saliency=result.location_saliency,
        available=True,
    )


@router.post("/contextualize", response_model=ContextualizeResponse)
async def contextualize_inscription(
    request: ContextualizeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Find similar inscriptions in the corpus.

    Args:
        text: The inscription text
        language: 'greek' or 'latin' (default: greek)
        top_k: Number of similar inscriptions to return (default: 20)

    Uses the model's embedding space to find semantically similar inscriptions.
    """
    service = get_ithaca_service()

    if not service.is_available(request.language):
        return ContextualizeResponse(
            similar=[],
            language=request.language,
            available=False,
            message=f"{request.language.title()} model not loaded. Check /api/inscriptions/model/status",
        )

    result = service.contextualize(
        request.text, language=request.language, top_k=request.top_k
    )

    return ContextualizeResponse(
        similar=[
            SimilarText(
                id=str(s.id),
                ids_alt=s.ids_alt,
                text=s.text,
                location_id=s.location_id,
                date_min=s.date_min,
                date_max=s.date_max,
                score=s.score,
                partner_link=s.partner_link,
            )
            for s in result.similar
        ],
        language=request.language,
        available=True,
    )


@router.get("/model/status")
async def get_model_status():
    """
    Check the status of all inscription models (Greek and Latin).
    """
    service = get_ithaca_service()
    status = service.get_status()

    return {
        "models": status,
        "features": ["restore", "attribute", "contextualize"],
        "supported_languages": ["greek", "latin"],
    }


@router.post("/model/initialize")
async def initialize_models(
    language: Optional[Language] = Query(
        None, description="Specific language to initialize, or omit for both"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    Initialize inscription analysis models.

    Args:
        language: 'greek', 'latin', or omit to initialize both

    This loads the model checkpoint and required data files.
    May take 30-60 seconds per model.
    """
    service = get_ithaca_service()

    if language:
        # Initialize specific language
        success = service.initialize_model(language)
        if success:
            return {
                "status": "success",
                "message": f"{language.title()} model initialized",
                "initialized": {language: True},
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize {language} model. Check that model files exist in backend/models/",
            )
    else:
        # Initialize both
        results = initialize_all_models()
        return {
            "status": "success" if any(results.values()) else "failed",
            "message": "Model initialization complete",
            "initialized": results,
        }
