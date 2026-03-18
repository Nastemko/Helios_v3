"""API endpoints for browsing and retrieving texts"""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models.text import (
    Language,
    LiteraryText,
    LiteraryTextLangVersion,
    TextSegment,
)

router = APIRouter(prefix="/api/texts", tags=["texts"])

ALLOWED_LANGUAGES = [Language.GRC, Language.LAT]


class TextResponse(BaseModel):
    """Flat text response matching the frontend Text interface."""

    id: int
    local_id: str
    author: str
    title: str
    language: str
    is_fragment: bool = False

    class Config:
        from_attributes = True


class TextSegmentResponse(BaseModel):
    """Text segment response."""

    id: int
    book: Optional[str] = None
    line: Optional[str] = None
    reference: str
    content: str
    sequence: int

    class Config:
        from_attributes = True


class TextDetailResponse(BaseModel):
    """Text detail with segments, matching the frontend TextDetail interface."""

    text: TextResponse
    segments: List[TextSegmentResponse]
    total_segments: int


@router.get("/authors/list")
async def list_authors(db: Session = Depends(get_db)):
    """
    Get list of authors that have Greek or Latin texts.

    Returns unique authors with a count of their available texts.
    """
    authors = (
        db.query(
            LiteraryText.author,
            func.count(LiteraryTextLangVersion.id).label("work_count"),
        )
        .join(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.language.in_(ALLOWED_LANGUAGES))
        .group_by(LiteraryText.author)
        .order_by(LiteraryText.author)
        .all()
    )

    return [{"author": author, "work_count": count} for author, count in authors]


@router.get("/stats/summary")
async def get_stats(db: Session = Depends(get_db)):
    """
    Get database statistics for Greek and Latin texts.
    """
    base_filter = LiteraryTextLangVersion.language.in_(ALLOWED_LANGUAGES)

    total_texts = (
        db.query(LiteraryTextLangVersion).filter(base_filter).count()
    )

    total_segments = (
        db.query(TextSegment)
        .join(LiteraryTextLangVersion)
        .filter(base_filter)
        .count()
    )

    versions_by_language = (
        db.query(
            LiteraryTextLangVersion.language,
            func.count(LiteraryTextLangVersion.id).label("count"),
        )
        .filter(base_filter)
        .group_by(LiteraryTextLangVersion.language)
        .all()
    )

    total_authors = (
        db.query(func.count(func.distinct(LiteraryText.author)))
        .join(LiteraryTextLangVersion)
        .filter(base_filter)
        .scalar()
    )

    return {
        "total_texts": total_texts,
        "total_segments": total_segments,
        "total_authors": total_authors,
        "texts_by_language": {
            lang.value: count for lang, count in versions_by_language
        },
    }


@router.get("/", response_model=List[TextResponse])
async def list_texts(
    search: Optional[str] = Query(None, description="Search by author or title"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    language: Optional[str] = Query(
        None, description="Filter by language (grc, lat)"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        50, ge=1, le=100, description="Maximum number of records to return"
    ),
    db: Session = Depends(get_db),
):
    """
    List Greek and Latin texts available for reading.

    Each entry is a specific language edition of a literary work.
    """
    query = (
        db.query(LiteraryTextLangVersion)
        .join(LiteraryText)
        .options(joinedload(LiteraryTextLangVersion.literary_text))
        .filter(LiteraryTextLangVersion.language.in_(ALLOWED_LANGUAGES))
    )

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                LiteraryText.author.ilike(search_pattern),
                LiteraryText.title.ilike(search_pattern),
            )
        )

    if author:
        author_pattern = f"%{author}%"
        query = query.filter(LiteraryText.author.ilike(author_pattern))

    if language:
        try:
            lang_enum = Language(language.lower())
            if lang_enum in ALLOWED_LANGUAGES:
                query = query.filter(
                    LiteraryTextLangVersion.language == lang_enum
                )
        except ValueError:
            pass

    query = query.order_by(LiteraryText.author, LiteraryText.title)
    versions = query.offset(skip).limit(limit).all()

    return [
        TextResponse(
            id=v.id,
            local_id=v.local_id,
            author=v.literary_text.author,
            title=v.literary_text.title,
            language=v.language.value,
        )
        for v in versions
    ]


@router.get("/{text_id}", response_model=TextDetailResponse)
async def get_text(
    text_id: Annotated[int, Path()],
    skip: int = Query(0, ge=0, description="Skip segments (for pagination)"),
    limit: int = Query(1000, ge=1, le=5000, description="Limit segments"),
    db: Session = Depends(get_db),
):
    """
    Get a text with its segments.

    The text_id refers to a specific language edition.
    """
    version = (
        db.query(LiteraryTextLangVersion)
        .options(joinedload(LiteraryTextLangVersion.literary_text))
        .filter(LiteraryTextLangVersion.id == text_id)
        .first()
    )

    if not version:
        raise HTTPException(status_code=404, detail=f"Text not found: {text_id}")

    segments_query = (
        db.query(TextSegment)
        .filter(TextSegment.lang_version_id == version.id)
        .order_by(TextSegment.sequence)
    )

    total_segments = segments_query.count()
    segments = segments_query.offset(skip).limit(limit).all()

    work = version.literary_text

    return TextDetailResponse(
        text=TextResponse(
            id=version.id,
            local_id=version.local_id,
            author=work.author,
            title=work.title,
            language=version.language.value,
        ),
        segments=[
            TextSegmentResponse.model_validate(seg, extra="ignore")
            for seg in segments
        ],
        total_segments=total_segments,
    )


@router.get("/{text_id}/segment/{reference}")
async def get_segment(
    text_id: Annotated[int, Path()],
    reference: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific segment by reference (e.g. '1.1' for book 1, line 1).
    """
    version = (
        db.query(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.id == text_id)
        .first()
    )

    if not version:
        raise HTTPException(status_code=404, detail=f"Text not found: {text_id}")

    segment = (
        db.query(TextSegment)
        .filter(
            TextSegment.lang_version_id == version.id,
            TextSegment.reference == reference,
        )
        .first()
    )

    if not segment:
        raise HTTPException(status_code=404, detail=f"Segment not found: {reference}")

    return TextSegmentResponse.model_validate(segment, extra="ignore")
