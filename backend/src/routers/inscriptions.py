"""API endpoints for browsing and querying PHI inscriptions"""
from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from pydantic import BaseModel

from database import get_db
from models.text import Text, TextSegment
from services.ithaca_service import get_ithaca_service, initialize_all_models

router = APIRouter(prefix="/api/inscriptions", tags=["inscriptions"])

# Type alias for language
Language = Literal["greek", "latin"]


# Response models
class InscriptionResponse(BaseModel):
    """Inscription metadata response"""
    id: int
    phi_id: int
    urn: str
    title: str
    text: str  # Full inscription text
    region_main: Optional[str] = None
    region_sub: Optional[str] = None
    date_str: Optional[str] = None
    date_min: Optional[int] = None
    date_max: Optional[int] = None
    date_circa: Optional[bool] = None
    metadata_raw: Optional[str] = None
    
    class Config:
        from_attributes = True


class InscriptionListItem(BaseModel):
    """Inscription list item (lighter version)"""
    id: int
    phi_id: int
    urn: str
    title: str
    text_preview: str  # First ~100 chars
    region_main: Optional[str] = None
    region_sub: Optional[str] = None
    date_str: Optional[str] = None
    date_min: Optional[int] = None
    date_max: Optional[int] = None
    
    class Config:
        from_attributes = True


class RegionCount(BaseModel):
    """Region with inscription count"""
    region: str
    region_id: Optional[str] = None
    count: int


class InscriptionStats(BaseModel):
    """Statistics about the inscription corpus"""
    total_inscriptions: int
    inscriptions_with_dates: int
    regions_count: int
    date_range: dict


def _get_inscription_metadata(text: Text) -> dict:
    """Extract metadata from text_metadata JSON field"""
    meta = text.text_metadata or {}
    return {
        "phi_id": meta.get("phi_id"),
        "region_main": meta.get("region_main"),
        "region_main_id": meta.get("region_main_id"),
        "region_sub": meta.get("region_sub"),
        "region_sub_id": meta.get("region_sub_id"),
        "date_str": meta.get("date_str"),
        "date_min": _parse_int(meta.get("date_min")),
        "date_max": _parse_int(meta.get("date_max")),
        "date_circa": meta.get("date_circa"),
        "metadata_raw": meta.get("metadata_raw"),
    }


def _parse_int(val) -> Optional[int]:
    """Safely parse int from string or return None"""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _get_full_text(db: Session, text_id: int) -> str:
    """Get full inscription text by joining segments"""
    segments = db.query(TextSegment).filter(
        TextSegment.text_id == text_id
    ).order_by(TextSegment.sequence).all()
    
    return ". ".join(seg.content for seg in segments if seg.content)


@router.get("/", response_model=List[InscriptionListItem])
async def list_inscriptions(
    search: Optional[str] = Query(None, description="Search in text content"),
    region_main: Optional[str] = Query(None, description="Filter by main region"),
    region_sub: Optional[str] = Query(None, description="Filter by sub-region"),
    date_min: Optional[int] = Query(None, description="Minimum date (negative = BC)"),
    date_max: Optional[int] = Query(None, description="Maximum date (negative = BC)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of records"),
    db: Session = Depends(get_db)
):
    """
    List and search inscriptions with filtering options.
    
    Date format: negative values are BC (e.g., -350 = 350 BC), positive are AD.
    """
    # Base query - only inscriptions (urn starts with urn:phi:)
    query = db.query(Text).filter(Text.urn.like('urn:phi:%'))
    
    # Search in text content
    if search:
        # Get texts that have matching segments
        search_pattern = f"%{search}%"
        matching_text_ids = db.query(TextSegment.text_id).filter(
            TextSegment.content.ilike(search_pattern)
        ).distinct().subquery()
        query = query.filter(Text.id.in_(matching_text_ids))
    
    # Region filters - need to check JSON metadata
    # For SQLite compatibility, we use text matching on the JSON string
    if region_main:
        query = query.filter(
            cast(Text.text_metadata, String).ilike(f'%"region_main": "{region_main}"%')
        )
    
    if region_sub:
        query = query.filter(
            cast(Text.text_metadata, String).ilike(f'%"region_sub": "{region_sub}"%')
        )
    
    # Apply pagination
    query = query.order_by(Text.id)
    texts = query.offset(skip).limit(limit).all()
    
    # Build response with text previews
    results = []
    for text in texts:
        meta = _get_inscription_metadata(text)
        
        # Filter by date if specified (post-filter since JSON querying is complex)
        if date_min is not None and meta["date_max"] is not None:
            if meta["date_max"] < date_min:
                continue
        if date_max is not None and meta["date_min"] is not None:
            if meta["date_min"] > date_max:
                continue
        
        # Get text preview from first segment
        first_segment = db.query(TextSegment).filter(
            TextSegment.text_id == text.id
        ).order_by(TextSegment.sequence).first()
        
        text_preview = ""
        if first_segment and first_segment.content:
            text_preview = first_segment.content[:150]
            if len(first_segment.content) > 150:
                text_preview += "..."
        
        results.append(InscriptionListItem(
            id=text.id,
            phi_id=meta["phi_id"] or 0,
            urn=text.urn,
            title=text.title,
            text_preview=text_preview,
            region_main=meta["region_main"],
            region_sub=meta["region_sub"],
            date_str=meta["date_str"],
            date_min=meta["date_min"],
            date_max=meta["date_max"],
        ))
    
    return results


@router.get("/regions", response_model=List[RegionCount])
async def list_regions(
    level: str = Query("main", description="Region level: 'main' or 'sub'"),
    db: Session = Depends(get_db)
):
    """
    Get list of regions with inscription counts.
    
    Use level='main' for top-level regions (e.g., 'Attica (IG I-III)'),
    or level='sub' for sub-regions (e.g., 'Athens: Agora').
    """
    # Get all inscription texts
    inscriptions = db.query(Text).filter(Text.urn.like('urn:phi:%')).all()
    
    # Count by region
    region_counts = {}
    for text in inscriptions:
        meta = text.text_metadata or {}
        if level == "main":
            region = meta.get("region_main")
            region_id = meta.get("region_main_id")
        else:
            region = meta.get("region_sub")
            region_id = meta.get("region_sub_id")
        
        if region:
            if region not in region_counts:
                region_counts[region] = {"count": 0, "region_id": region_id}
            region_counts[region]["count"] += 1
    
    # Sort by count descending
    results = [
        RegionCount(region=region, region_id=data["region_id"], count=data["count"])
        for region, data in sorted(region_counts.items(), key=lambda x: -x[1]["count"])
    ]
    
    return results


@router.get("/stats", response_model=InscriptionStats)
async def get_inscription_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the inscription corpus.
    """
    # Count total inscriptions
    total = db.query(Text).filter(Text.urn.like('urn:phi:%')).count()
    
    # Get all inscriptions to analyze metadata
    inscriptions = db.query(Text).filter(Text.urn.like('urn:phi:%')).all()
    
    dated_count = 0
    regions = set()
    all_date_mins = []
    all_date_maxs = []
    
    for text in inscriptions:
        meta = text.text_metadata or {}
        
        if meta.get("region_main"):
            regions.add(meta["region_main"])
        
        date_min = _parse_int(meta.get("date_min"))
        date_max = _parse_int(meta.get("date_max"))
        
        if date_min is not None or date_max is not None:
            dated_count += 1
            if date_min is not None:
                all_date_mins.append(date_min)
            if date_max is not None:
                all_date_maxs.append(date_max)
    
    return InscriptionStats(
        total_inscriptions=total,
        inscriptions_with_dates=dated_count,
        regions_count=len(regions),
        date_range={
            "earliest": min(all_date_mins) if all_date_mins else None,
            "latest": max(all_date_maxs) if all_date_maxs else None,
        }
    )


@router.get("/{phi_id}", response_model=InscriptionResponse)
async def get_inscription(
    phi_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific inscription by its PHI ID.
    """
    urn = f"urn:phi:{phi_id}"
    text = db.query(Text).filter(Text.urn == urn).first()
    
    if not text:
        raise HTTPException(status_code=404, detail=f"Inscription not found: PHI {phi_id}")
    
    meta = _get_inscription_metadata(text)
    full_text = _get_full_text(db, text.id)
    
    return InscriptionResponse(
        id=text.id,
        phi_id=meta["phi_id"] or phi_id,
        urn=text.urn,
        title=text.title,
        text=full_text,
        region_main=meta["region_main"],
        region_sub=meta["region_sub"],
        date_str=meta["date_str"],
        date_min=meta["date_min"],
        date_max=meta["date_max"],
        date_circa=meta["date_circa"],
        metadata_raw=meta["metadata_raw"],
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


class SimilarInscription(BaseModel):
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
    similar: List[SimilarInscription]
    language: str
    available: bool
    message: Optional[str] = None


@router.post("/restore", response_model=RestoreResponse)
async def restore_inscription(request: RestoreRequest):
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
            message=f"{request.language.title()} model not loaded. Check /api/inscriptions/model/status"
        )
    
    result = service.restore(
        text=request.text,
        language=request.language,
        beam_width=request.beam_width,
        temperature=request.temperature,
        max_restoration_len=request.max_restoration_len
    )
    
    return RestoreResponse(
        input_text=result.input_text,
        language=request.language,
        top_prediction=result.top_prediction,
        missing_indices=result.missing_indices,
        predictions=[
            RestorationCandidate(
                text=p.text,
                restored_indices=p.restored_indices,
                score=p.score
            )
            for p in result.predictions
        ],
        prediction_saliency=result.prediction_saliency,
        available=True
    )


@router.post("/attribute", response_model=AttributeResponse)
async def attribute_inscription(request: AttributeRequest):
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
            message=f"{request.language.title()} model not loaded. Check /api/inscriptions/model/status"
        )
    
    result = service.attribute(request.text, language=request.language)
    
    return AttributeResponse(
        input_text=result.input_text,
        language=request.language,
        locations=[
            LocationPrediction(
                location_id=loc.location_id,
                name=loc.name,
                score=loc.score
            )
            for loc in result.locations
        ],
        year_scores=result.year_scores,
        predicted_date_range=result.predicted_date_range,
        date_saliency=result.date_saliency,
        location_saliency=result.location_saliency,
        available=True
    )


@router.post("/contextualize", response_model=ContextualizeResponse)
async def contextualize_inscription(request: ContextualizeRequest):
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
            message=f"{request.language.title()} model not loaded. Check /api/inscriptions/model/status"
        )
    
    result = service.contextualize(
        request.text, 
        language=request.language,
        top_k=request.top_k
    )
    
    return ContextualizeResponse(
        similar=[
            SimilarInscription(
                id=str(s.id),
                ids_alt=s.ids_alt,
                text=s.text,
                location_id=s.location_id,
                date_min=s.date_min,
                date_max=s.date_max,
                score=s.score,
                partner_link=s.partner_link
            )
            for s in result.similar
        ],
        language=request.language,
        available=True
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
        "supported_languages": ["greek", "latin"]
    }


@router.post("/model/initialize")
async def initialize_models(
    language: Optional[Language] = Query(None, description="Specific language to initialize, or omit for both")
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
                "initialized": {language: True}
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize {language} model. Check that model files exist in backend/models/"
            )
    else:
        # Initialize both
        results = initialize_all_models()
        return {
            "status": "success" if any(results.values()) else "failed",
            "message": "Model initialization complete",
            "initialized": results
        }
