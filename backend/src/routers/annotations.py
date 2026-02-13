"""API endpoints for user annotations"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_serializer
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.annotation import Annotation
from models.text import LiteraryText, TextSegment
from models.user import User

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


# Request/Response models
class AnnotationCreate(BaseModel):
    """Request model for creating an annotation"""

    text_id: int
    segment_id: int
    word: str
    note: str


class AnnotationUpdate(BaseModel):
    """Request model for updating an annotation"""

    note: str


class AnnotationResponse(BaseModel):
    """Response model for annotation"""

    id: int
    user_id: int
    text_id: int
    segment_id: int
    word: str
    note: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None


@router.post("/", response_model=AnnotationResponse, status_code=201)
async def create_annotation(
    annotation: AnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new annotation

    User must be authenticated. The annotation will be associated with the current user.
    """
    # Verify text exists

    text = db.query(LiteraryText).filter(LiteraryText.id == annotation.text_id).scalar()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")

    segment = (
        db.query(TextSegment)
        .filter(TextSegment.text_id == text.id, TextSegment.id == annotation.segment_id)
        .scalar()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Text segment not found")

    # Create annotation
    db_annotation = Annotation(
        user_id=current_user.id,
        text_id=annotation.text_id,
        segment_id=annotation.segment_id,
        word=annotation.word,
        note=annotation.note,
    )

    db.add(db_annotation)
    db.commit()
    db.refresh(db_annotation)

    return AnnotationResponse.model_validate(db_annotation)


@router.get("/", response_model=List[AnnotationResponse])
async def list_annotations(
    text_id: Optional[int] = Query(None, description="Filter by text ID"),
    segment_id: Optional[int] = Query(None, description="Filter by segment ID"),
    word: Optional[str] = Query(None, description="Filter by word"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List user's annotations

    Returns only annotations belonging to the authenticated user.
    Optional filters for text, segment, or specific word.
    """
    query = db.query(Annotation).filter(Annotation.user_id == current_user.id)

    # Apply filters
    if text_id:
        query = query.filter(Annotation.text_id == text_id)

    if segment_id:
        query = query.filter(Annotation.segment_id == segment_id)

    if word:
        query = query.filter(Annotation.word == word)

    # Order by most recent first
    query = query.order_by(Annotation.created_at.desc())

    # Apply pagination
    annotations = query.offset(skip).limit(limit).all()

    return [AnnotationResponse.model_validate(ann) for ann in annotations]


@router.get("/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific annotation

    Only the owner of the annotation can retrieve it.
    """
    annotation = (
        db.query(Annotation)
        .filter(Annotation.id == annotation_id, Annotation.user_id == current_user.id)
        .first()
    )

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    return AnnotationResponse.model_validate(annotation, extra="ignore")


@router.put("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: int,
    annotation_update: AnnotationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update an annotation

    Only the owner of the annotation can update it.
    """
    annotation = (
        db.query(Annotation)
        .filter(Annotation.id == annotation_id, Annotation.user_id == current_user.id)
        .first()
    )

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Update the note
    annotation.note = annotation_update.note

    db.commit()
    db.refresh(annotation)

    return AnnotationResponse.model_validate(annotation, extra="ignore")


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete an annotation

    Only the owner of the annotation can delete it.
    """
    annotation = (
        db.query(Annotation)
        .filter(Annotation.id == annotation_id, Annotation.user_id == current_user.id)
        .first()
    )

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    db.delete(annotation)
    db.commit()

    return None


@router.get("/text/{text_id}/summary")
async def get_text_annotations_summary(
    text_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get summary of annotations for a text

    Returns count of annotations and most annotated words.
    """
    text = db.query(LiteraryText).filter(LiteraryText.id == text_id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")

    # Get total count
    total = (
        db.query(Annotation)
        .filter(Annotation.user_id == current_user.id, Annotation.text_id == text_id)
        .count()
    )

    # Get most annotated words
    most_annotated = (
        db.query(Annotation.word, func.count(Annotation.id).label("count"))
        .filter(Annotation.user_id == current_user.id, Annotation.text_id == text_id)
        .group_by(Annotation.word)
        .order_by(func.count(Annotation.id).desc())
        .limit(10)
        .all()
    )

    return {
        "text_id": text_id,
        "total_annotations": total,
        "most_annotated_words": [
            {"word": word, "count": count} for word, count in most_annotated
        ],
    }
