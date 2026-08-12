"""API endpoints for browsing and querying PHI inscriptions"""

import logging
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.inscription import Inscription, InscriptionSegment
from models.user import User
from services.ithaca_client import (
    DEFAULT_BEAM_WIDTH,
    DEFAULT_MAX_RESTORATION_LEN,
    MAX_BEAM_WIDTH,
    MAX_RESTORATION_LEN,
    MAX_TOP_K,
    get_ithaca_client,
)

logger = logging.getLogger(__name__)

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
    # JSONB column: the residual PHI fields that have no dedicated column.
    metadata_raw: Optional[Dict[str, Any]] = None

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


class _InscriptionTextRequest(BaseModel):
    """Shared gap-notation validation for the model endpoints.

    The model takes '?' for one missing character and '#' for a gap of unknown
    length (vendor/predictingthepast/eval/inference.py:199-200). '-' is the
    model's *internal* spelling of '?', not user notation: it is in the
    vocabulary, so it tokenizes without error but never enters
    ``restore_mask_idx`` and is therefore never filled. Rejecting it here turns
    a silent no-op into a message that teaches the notation.
    """

    text: str

    @field_validator("text", mode="after")
    @classmethod
    def reject_internal_markers(cls, value: str) -> str:
        if "-" in value:
            raise ValueError(
                "Use '?' for each missing character (e.g. '?????' for five) "
                "and '#' for a gap of unknown length. '-' is not supported."
            )
        return value


class RestoreRequest(_InscriptionTextRequest):
    """Request for text restoration"""

    language: Language = "greek"
    temperature: float = 1.0
    beam_width: int = Field(
        DEFAULT_BEAM_WIDTH,
        ge=1,
        le=MAX_BEAM_WIDTH,
        description=(
            "Number of candidates kept during beam search. Higher is slower; "
            "cost is roughly linear in this value."
        ),
    )
    # Upper bound matches UNK_RESTORATION_MAX_LEN in the vendored inference
    # module, which raises above it.
    max_restoration_len: int = Field(
        DEFAULT_MAX_RESTORATION_LEN,
        ge=1,
        le=MAX_RESTORATION_LEN,
        description=(
            "Longest gap, in characters, that a '#' may be restored to. Only "
            "affects inputs containing '#'. Lower is much faster -- set it to "
            "your estimate of the lacuna size."
        ),
    )


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


class AttributeRequest(_InscriptionTextRequest):
    """Request for attribution (date + location)"""

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


class ContextualizeRequest(_InscriptionTextRequest):
    """Request for finding similar inscriptions"""

    language: Language = "greek"
    # Bounded now that this crosses a network: an unbounded top_k was merely a
    # long list in-process, but is a response-size and serialisation cost once
    # the results have to come back over the wire.
    top_k: int = Field(20, ge=1, le=MAX_TOP_K)


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
def restore_inscription(
    request: RestoreRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Restore missing characters in an inscription.

    Use one '?' per missing character ('?????' is exactly five) and '#' for a
    gap whose length is unknown. '-' is rejected: see _InscriptionTextRequest.

    A '#' is much more expensive than '?': it searches over how long the gap is
    as well as what fills it, so one '#' takes ~30 forward passes where nine '?'
    take 9. If you know roughly how large the lacuna is, pass
    max_restoration_len set just above it -- headroom far past the true gap is
    still searched and still costs, but a cap below it forces a worse (and not
    necessarily faster) restoration.

    Args:
        text: The inscription text with missing characters
        language: 'greek' or 'latin' (default: greek)
        temperature: Sampling temperature (default: 1.0)
        beam_width: Candidates kept during search (default: 35, max 100)
        max_restoration_len: Longest gap a '#' may expand to
            (default: 15, max 20). Ignored when the text has no '#'.

    Example Greek: "εδοξεν τηι βουληι και τωι δημωι # αθηναιων"
    Example Latin: "imp caesar divi # f augustus"
    """
    # beam_width and max_restoration_len are bounded by Field(ge=..., le=...) on
    # RestoreRequest, so an out-of-range value is a 422 rather than an unbounded
    # amount of compute. Both were previously taken straight from the request body.
    #
    # No availability pre-check and no inference lock any more. The pre-check
    # cost a second round trip to say what the call itself reports, and
    # serialising inference is now the inference service's concern -- it runs at
    # concurrency 1 and the platform queues, so a busy model delays a request
    # rather than rejecting it with a 429.
    client = get_ithaca_client()
    result = client.restore(
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
        available=result.available,
        message=result.message,
    )


@router.post("/attribute", response_model=AttributeResponse)
def attribute_inscription(
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
    client = get_ithaca_client()
    result = client.attribute(request.text, language=request.language)

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
        available=result.available,
        message=result.message,
    )


@router.post("/contextualize", response_model=ContextualizeResponse)
def contextualize_inscription(
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
    client = get_ithaca_client()
    result = client.contextualize(
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
        available=result.available,
        message=result.message,
    )


@router.get("/model/status")
async def get_model_status():
    """
    Check the status of all inscription models (Greek and Latin).
    """
    # Reports the inference service's view, not this process's. A service that
    # cannot be reached reads as both models unavailable, which is what a
    # caller needs to know: from here an unreachable model and an unloaded one
    # have the same consequence.
    status = get_ithaca_client().get_status()

    return {
        "models": status,
        "features": ["restore", "attribute", "contextualize"],
        "supported_languages": ["greek", "latin"],
    }
