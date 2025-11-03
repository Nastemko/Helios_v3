"""API endpoints for browsing and retrieving texts"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from database import get_db
from models.text import Text, TextSegment

router = APIRouter(prefix="/api/texts", tags=["texts"])


# Response models
class TextResponse(BaseModel):
    """Text metadata response"""
    id: int
    urn: str
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
    language: Optional[str] = Query(None, description="Filter by language (grc, lat)"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    is_fragment: Optional[bool] = Query(None, description="Filter fragments"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    List and search available texts
    
    Returns paginated list of texts with optional filtering.
    """
    query = db.query(Text)
    
    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Text.author.ilike(search_pattern),
                Text.title.ilike(search_pattern)
            )
        )
    
    if language:
        query = query.filter(Text.language == language)
    
    if author:
        author_pattern = f"%{author}%"
        query = query.filter(Text.author.ilike(author_pattern))
    
    if is_fragment is not None:
        query = query.filter(Text.is_fragment == is_fragment)
    
    # Order by author and title
    query = query.order_by(Text.author, Text.title)
    
    # Apply pagination
    texts = query.offset(skip).limit(limit).all()
    
    return texts


@router.get("/{urn:path}", response_model=TextDetailResponse)
async def get_text(
    urn: str,
    skip: int = Query(0, ge=0, description="Skip segments (for pagination)"),
    limit: int = Query(1000, ge=1, le=5000, description="Limit segments"),
    db: Session = Depends(get_db)
):
    """
    Get a specific text with its segments
    
    The URN may contain slashes, so we use path parameter.
    Example: urn:cts:greekLit:tlg0012.tlg001
    """
    # Find text by URN
    text = db.query(Text).filter(Text.urn == urn).first()
    
    if not text:
        raise HTTPException(status_code=404, detail=f"Text not found: {urn}")
    
    # Get segments with pagination
    segments_query = db.query(TextSegment).filter(
        TextSegment.text_id == text.id
    ).order_by(TextSegment.sequence)
    
    total_segments = segments_query.count()
    segments = segments_query.offset(skip).limit(limit).all()
    
    return TextDetailResponse(
        text=TextResponse.from_orm(text),
        segments=[TextSegmentResponse.from_orm(seg) for seg in segments],
        total_segments=total_segments
    )


@router.get("/{urn:path}/segment/{reference}")
async def get_text_segment(
    urn: str,
    reference: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific segment of a text by reference
    
    Example: /api/texts/urn:cts:greekLit:tlg0012.tlg001/segment/1.1
    Returns book 1, line 1 of the Iliad
    """
    # Find text
    text = db.query(Text).filter(Text.urn == urn).first()
    
    if not text:
        raise HTTPException(status_code=404, detail=f"Text not found: {urn}")
    
    # Find segment by reference
    segment = db.query(TextSegment).filter(
        TextSegment.text_id == text.id,
        TextSegment.reference == reference
    ).first()
    
    if not segment:
        raise HTTPException(
            status_code=404,
            detail=f"Segment not found: {reference}"
        )
    
    return TextSegmentResponse.from_orm(segment)


@router.get("/{urn:path}/segments/range")
async def get_text_segments_range(
    urn: str,
    start: str = Query(..., description="Start reference (e.g., '1.1')"),
    end: str = Query(..., description="End reference (e.g., '1.10')"),
    db: Session = Depends(get_db)
):
    """
    Get a range of segments from a text
    
    Example: /api/texts/urn:cts:greekLit:tlg0012.tlg001/segments/range?start=1.1&end=1.10
    Returns lines 1-10 of book 1
    """
    # Find text
    text = db.query(Text).filter(Text.urn == urn).first()
    
    if not text:
        raise HTTPException(status_code=404, detail=f"Text not found: {urn}")
    
    # Find start and end segments
    start_seg = db.query(TextSegment).filter(
        TextSegment.text_id == text.id,
        TextSegment.reference == start
    ).first()
    
    end_seg = db.query(TextSegment).filter(
        TextSegment.text_id == text.id,
        TextSegment.reference == end
    ).first()
    
    if not start_seg:
        raise HTTPException(status_code=404, detail=f"Start segment not found: {start}")
    
    if not end_seg:
        raise HTTPException(status_code=404, detail=f"End segment not found: {end}")
    
    # Get all segments in range
    segments = db.query(TextSegment).filter(
        TextSegment.text_id == text.id,
        TextSegment.sequence >= start_seg.sequence,
        TextSegment.sequence <= end_seg.sequence
    ).order_by(TextSegment.sequence).all()
    
    return [TextSegmentResponse.from_orm(seg) for seg in segments]


@router.get("/authors/list")
async def list_authors(db: Session = Depends(get_db)):
    """
    Get list of all authors in the database
    
    Returns list of unique authors with count of their works
    """
    from sqlalchemy import func
    
    authors = db.query(
        Text.author,
        func.count(Text.id).label('work_count')
    ).group_by(Text.author).order_by(Text.author).all()
    
    return [
        {
            "author": author,
            "work_count": count
        }
        for author, count in authors
    ]


@router.get("/stats/summary")
async def get_stats(db: Session = Depends(get_db)):
    """
    Get database statistics
    
    Returns counts of texts, segments, languages, etc.
    """
    from sqlalchemy import func
    
    total_texts = db.query(Text).count()
    total_segments = db.query(TextSegment).count()
    
    texts_by_language = db.query(
        Text.language,
        func.count(Text.id).label('count')
    ).group_by(Text.language).all()
    
    fragment_count = db.query(Text).filter(Text.is_fragment == True).count()
    
    return {
        "total_texts": total_texts,
        "total_segments": total_segments,
        "texts_by_language": {lang: count for lang, count in texts_by_language},
        "fragment_count": fragment_count
    }

