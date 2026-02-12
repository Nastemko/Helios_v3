"""API endpoints for browsing and retrieving texts"""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models.text import LiteraryText, TextSegment, Language

router = APIRouter(prefix="/api/texts", tags=["texts"])


# Response models
class TextResponse(BaseModel):
    """Text metadata response"""

    id: int
    local_id: str
    author: str
    title: str
    language: str
    is_fragment: bool
    text_metadata: dict = {}

    class Config:
        from_attributes = True


class TextSegmentResponse(BaseModel):
    """Text segment response"""

    id: int
    book: str
    line: str
    reference: str
    content: str
    sequence: int

    class Config:
        from_attributes = True


class TextDetailResponse(BaseModel):
    """Detailed text response with segments"""

    text: TextResponse
    segments: List[TextSegmentResponse]
    total_segments: int


@router.get("/", response_model=List[TextResponse])
async def list_texts(
    search: Optional[str] = Query(None, description="Search by author or title"),
    language: Optional[str] = Query(
        None, description="Filter by language (grc, lat, en)"
    ),
    author: Optional[str] = Query(None, description="Filter by author name"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        50, ge=1, le=100, description="Maximum number of records to return"
    ),
    db: Session = Depends(get_db),
):
    """
    List and search available texts

    Returns paginated list of texts with optional filtering.
    """
    query = db.query(LiteraryText)

    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                LiteraryText.author.ilike(search_pattern),
                LiteraryText.title.ilike(search_pattern),
            )
        )

    if language:
        try:
            lang_enum = Language[language.upper()]
            query = query.filter(LiteraryText.language == lang_enum)
        except KeyError:
            pass

    if author:
        author_pattern = f"%{author}%"
        query = query.filter(LiteraryText.author.ilike(author_pattern))

    # Order by author and title
    query = query.order_by(LiteraryText.author, LiteraryText.title)

    # Apply pagination
    texts = query.offset(skip).limit(limit).all()

    return [TextResponse.model_validate(t, extra="ignore") for t in texts]


@router.get("/{text_id}", response_model=TextDetailResponse)
async def get_text(
    text_id: Annotated[int, Path()],
    skip: int = Query(0, ge=0, description="Skip segments (for pagination)"),
    limit: int = Query(1000, ge=1, le=5000, description="Limit segments"),
    db: Session = Depends(get_db),
):
    """
    Get a specific text with its segments

    Example: /api/texts/123
    """
    # Find text by ID
    text = db.query(LiteraryText).filter(LiteraryText.id == text_id).first()

    if not text:
        raise HTTPException(status_code=404, detail=f"Text not found: {text_id}")

    # Get segments with pagination
    segments_query = (
        db.query(TextSegment)
        .filter(TextSegment.text_id == text.id)
        .order_by(TextSegment.sequence)
    )

    total_segments = segments_query.count()
    segments = segments_query.offset(skip).limit(limit).all()

    return TextDetailResponse(
        text=TextResponse.model_validate(text, extra="ignore"),
        segments=[
            TextSegmentResponse.model_validate(seg, extra="ignore") for seg in segments
        ],
        total_segments=total_segments,
    )


@router.get("/{text_id}/segment/{reference}")
async def get_text_segment(
    text_id: Annotated[int, Path()], reference: str, db: Session = Depends(get_db)
):
    """
    Get a specific segment of a text by reference

    Example: /api/texts/123/segment/1.1
    Returns book 1, line 1 of the text
    """
    # Find text
    text = db.query(LiteraryText).filter(LiteraryText.id == text_id).first()

    if not text:
        raise HTTPException(status_code=404, detail=f"Text not found: {text_id}")

    # Find segment by reference
    segment = (
        db.query(TextSegment)
        .filter(TextSegment.text_id == text.id, TextSegment.reference == reference)
        .first()
    )

    if not segment:
        raise HTTPException(status_code=404, detail=f"Segment not found: {reference}")

    return TextSegmentResponse.model_validate(segment, extra="ignore")


@router.get("/authors/list")
async def list_authors(db: Session = Depends(get_db)):
    """
    Get list of all authors in the database

    Returns list of unique authors with count of their works
    """
    from sqlalchemy import func

    authors = (
        db.query(LiteraryText.author, func.count(LiteraryText.id).label("work_count"))
        .filter(LiteraryText.source == TextSource.GreekLit)
        .group_by(LiteraryText.author)
        .order_by(LiteraryText.author)
        .all()
    )

    return [{"author": author, "work_count": count} for author, count in authors]


@router.get("/stats/summary")
async def get_stats(db: Session = Depends(get_db)):
    """
    Get database statistics

    Returns counts of texts, segments, languages, etc.
    """
    from sqlalchemy import func

    total_texts = db.query(Text).count()
    total_segments = db.query(TextSegment).count()

    texts_by_language = (
        db.query(LiteraryText.language, func.count(LiteraryText.id).label("count"))
        .group_by(LiteraryText.language)
        .all()
    )

    fragment_count = db.query(Text).filter(LiteraryText.is_fragment).count()

    return {
        "total_texts": total_texts,
        "total_segments": total_segments,
        "texts_by_language": {lang: count for lang, count in texts_by_language},
        "fragment_count": fragment_count,
    }
