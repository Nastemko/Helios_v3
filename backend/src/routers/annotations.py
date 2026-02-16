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
from models.text import LiteraryTextLangVersion, TextSegment
from models.user import User

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    """Request model for creating an annotation"""

    lang_version_id: int
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
    lang_version_id: int
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
    version = (
        db.query(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.id == annotation.lang_version_id)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Text version not found")

    segment = (
        db.query(TextSegment)
        .filter(
            TextSegment.lang_version_id == version.id,
            TextSegment.id == annotation.segment_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Text segment not found")

    db_annotation = Annotation(
        user_id=current_user.id,
        lang_version_id=annotation.lang_version_id,
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
    lang_version_id: Optional[int] = Query(None, description="Filter by version ID"),
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
    Optional filters for version, segment, or specific word.
    """
    query = db.query(Annotation).filter(Annotation.user_id == current_user.id)

    if lang_version_id:
        query = query.filter(Annotation.lang_version_id == lang_version_id)

    if segment_id:
        query = query.filter(Annotation.segment_id == segment_id)

    if word:
        query = query.filter(Annotation.word == word)

    query = query.order_by(Annotation.created_at.desc())
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


@router.get("/version/{version_id}/summary")
async def get_version_annotations_summary(
    version_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get summary of annotations for a text version

    Returns count of annotations and most annotated words.
    """
    version = (
        db.query(LiteraryTextLangVersion)
        .filter(LiteraryTextLangVersion.id == version_id)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Text version not found")

    total = (
        db.query(Annotation)
        .filter(
            Annotation.user_id == current_user.id,
            Annotation.lang_version_id == version_id,
        )
        .count()
    )

    most_annotated = (
        db.query(Annotation.word, func.count(Annotation.id).label("count"))
        .filter(
            Annotation.user_id == current_user.id,
            Annotation.lang_version_id == version_id,
        )
        .group_by(Annotation.word)
        .order_by(func.count(Annotation.id).desc())
        .limit(10)
        .all()
    )

    return {
        "version_id": version_id,
        "total_annotations": total,
        "most_annotated_words": [
            {"word": word, "count": count} for word, count in most_annotated
        ],
    }
