"""API endpoints for browsing and retrieving texts"""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import get_db
from models.text import (
    Language,
    LiteraryText,
    LiteraryTextLangVersion,
    TextSegment,
)

router = APIRouter(prefix="/api/texts", tags=["texts"])


class LangVersionResponse(BaseModel):
    """Language version response (brief)"""

    id: int
    local_id: str
    language: str
    translator: Optional[str] = None

    class Config:
        from_attributes = True


class LiteraryTextResponse(BaseModel):
    """Literary work response (parent record)"""

    id: int
    local_id: str
    author: str
    title: str
    versions: List[LangVersionResponse] = []

    class Config:
        from_attributes = True


class TextSegmentResponse(BaseModel):
    """Text segment response"""

    id: int
    book: Optional[str] = None
    line: Optional[str] = None
    reference: str
    content: str
    sequence: int

    class Config:
        from_attributes = True


class LangVersionDetailResponse(BaseModel):
    """Detailed language version response with segments"""

    version: LangVersionResponse
    work: LiteraryTextResponse
    segments: List[TextSegmentResponse]
    total_segments: int


@router.get("/", response_model=List[LiteraryTextResponse])
async def list_works(
    search: Optional[str] = Query(None, description="Search by author or title"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        50, ge=1, le=100, description="Maximum number of records to return"
    ),
    db: Session = Depends(get_db),
):
    """
    List literary works (parent records)

    Each work can have multiple language versions (original + translations).
    """
    query = db.query(LiteraryText)

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

    query = query.order_by(LiteraryText.author, LiteraryText.title)
    works = query.offset(skip).limit(limit).all()

    return [
        LiteraryTextResponse(
            id=w.id,
            local_id=w.local_id,
            author=w.author,
            title=w.title,
            versions=[
                LangVersionResponse(
                    id=v.id,
                    local_id=v.local_id,
                    language=v.language.value,
                    translator=v.translator,
                )
                for v in w.lang_versions
            ],
        )
        for w in works
    ]


@router.get("/versions/", response_model=List[LangVersionResponse])
async def list_versions(
    language: Optional[str] = Query(
        None, description="Filter by language (grc, lat, en)"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    List language versions (specific translations/editions)

    Use this to browse all versions with a specific language filter.
    """
    query = db.query(LiteraryTextLangVersion)

    if language:
        try:
            lang_enum = Language(language.lower())
            query = query.filter(LiteraryTextLangVersion.language == lang_enum)
        except ValueError:
            pass

    query = query.order_by(LiteraryTextLangVersion.local_id)
    versions = query.offset(skip).limit(limit).all()

    return [
        LangVersionResponse(
            id=v.id,
            local_id=v.local_id,
            language=v.language.value,
            translator=v.translator,
        )
        for v in versions
    ]


@router.get("/{work_id}", response_model=LiteraryTextResponse)
async def get_work(
    work_id: Annotated[int, Path()],
    db: Session = Depends(get_db),
):
    """
    Get a specific work with all its language versions

    Example: /api/texts/123
    """
    work = db.query(LiteraryText).filter(LiteraryText.id == work_id).first()

    if not work:
        raise HTTPException(status_code=404, detail=f"Work not found: {work_id}")

    return LiteraryTextResponse(
        id=work.id,
        local_id=work.local_id,
        author=work.author,
        title=work.title,
        versions=[
            LangVersionResponse(
                id=v.id,
                local_id=v.local_id,
                language=v.language.value,
                translator=v.translator,
            )
            for v in work.lang_versions
        ],
    )


@router.get("/versions/{version_id}", response_model=LangVersionDetailResponse)
async def get_version(
    version_id: Annotated[int, Path()],
    skip: int = Query(0, ge=0, description="Skip segments (for pagination)"),
    limit: int = Query(1000, ge=1, le=5000, description="Limit segments"),
    db: Session = Depends(get_db),
):
    """
    Get a specific version with its segments

    Example: /api/texts/versions/456
    """
    version = (
        db.query(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.id == version_id)
        .first()
    )

    if not version:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")

    segments_query = (
        db.query(TextSegment)
        .filter(TextSegment.lang_version_id == version.id)
        .order_by(TextSegment.sequence)
    )

    total_segments = segments_query.count()
    segments = segments_query.offset(skip).limit(limit).all()

    work = version.literary_text

    return LangVersionDetailResponse(
        version=LangVersionResponse(
            id=version.id,
            local_id=version.local_id,
            language=version.language.value,
            translator=version.translator,
        ),
        work=LiteraryTextResponse(
            id=work.id,
            local_id=work.local_id,
            author=work.author,
            title=work.title,
            versions=[],
        ),
        segments=[
            TextSegmentResponse.model_validate(seg, extra="ignore") for seg in segments
        ],
        total_segments=total_segments,
    )


@router.get("/versions/{version_id}/segment/{reference}")
async def get_segment(
    version_id: Annotated[int, Path()],
    reference: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific segment of a version by reference

    Example: /api/texts/versions/456/segment/1.1
    Returns book 1, line 1 of the version
    """
    version = (
        db.query(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.id == version_id)
        .first()
    )

    if not version:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")

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


@router.get("/authors/list")
async def list_authors(db: Session = Depends(get_db)):
    """
    Get list of all authors in the database

    Returns list of unique authors with count of their works
    """
    authors = (
        db.query(LiteraryText.author, func.count(LiteraryText.id).label("work_count"))
        .group_by(LiteraryText.author)
        .order_by(LiteraryText.author)
        .all()
    )

    return [{"author": author, "work_count": count} for author, count in authors]


@router.get("/stats/summary")
async def get_stats(db: Session = Depends(get_db)):
    """
    Get database statistics

    Returns counts of works, versions, segments, languages, etc.
    """
    total_works = db.query(LiteraryText).count()
    total_versions = db.query(LiteraryTextLangVersion).count()
    total_segments = db.query(TextSegment).count()

    versions_by_language = (
        db.query(
            LiteraryTextLangVersion.language,
            func.count(LiteraryTextLangVersion.id).label("count"),
        )
        .group_by(LiteraryTextLangVersion.language)
        .all()
    )

    translation_count = (
        db.query(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.translator.isnot(None))
        .count()
    )

    return {
        "total_works": total_works,
        "total_versions": total_versions,
        "total_segments": total_segments,
        "versions_by_language": {
            lang.value if hasattr(lang, "value") else str(lang): count
            for lang, count in versions_by_language
        },
        "translation_count": translation_count,
        "original_count": total_versions - translation_count,
    }
