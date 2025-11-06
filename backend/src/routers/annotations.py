"""API endpoints for user annotations"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database import get_db
from src.models.user import User
from src.models.annotation import Annotation
from src.middleware.auth import get_current_user

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
    created_at: str
    updated_at: Optional[str] = None
    
    @classmethod
    def from_annotation(cls, annotation: Annotation) -> 'AnnotationResponse':
        """Create response from annotation model with datetime serialization"""
        return cls(
            id=annotation.id,
            user_id=annotation.user_id,
            text_id=annotation.text_id,
            segment_id=annotation.segment_id,
            word=annotation.word,
            note=annotation.note,
            created_at=annotation.created_at.isoformat() if annotation.created_at else "",
            updated_at=annotation.updated_at.isoformat() if annotation.updated_at else None
        )
    
    class Config:
        from_attributes = True


@router.post("/", response_model=AnnotationResponse, status_code=201)
async def create_annotation(
    annotation: AnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new annotation
    
    User must be authenticated. The annotation will be associated with the current user.
    """
    # Verify text exists
    from src.models.text import Text, TextSegment
    
    text = db.query(Text).filter(Text.id == annotation.text_id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    
    segment = db.query(TextSegment).filter(TextSegment.id == annotation.segment_id).first()
    if not segment:
        raise HTTPException(status_code=404, detail="Text segment not found")
    
    # Verify segment belongs to text
    if segment.text_id != text.id:
        raise HTTPException(
            status_code=400,
            detail="Segment does not belong to specified text"
        )
    
    # Create annotation
    db_annotation = Annotation(
        user_id=current_user.id,
        text_id=annotation.text_id,
        segment_id=annotation.segment_id,
        word=annotation.word,
        note=annotation.note
    )
    
    db.add(db_annotation)
    db.commit()
    db.refresh(db_annotation)
    
    return AnnotationResponse.from_annotation(db_annotation)


@router.get("/", response_model=List[AnnotationResponse])
async def list_annotations(
    text_id: Optional[int] = Query(None, description="Filter by text ID"),
    segment_id: Optional[int] = Query(None, description="Filter by segment ID"),
    word: Optional[str] = Query(None, description="Filter by word"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    
    return [AnnotationResponse.from_annotation(ann) for ann in annotations]


@router.get("/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific annotation
    
    Only the owner of the annotation can retrieve it.
    """
    annotation = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()
    
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    return AnnotationResponse.from_annotation(annotation)


@router.put("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: int,
    annotation_update: AnnotationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an annotation
    
    Only the owner of the annotation can update it.
    """
    annotation = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()
    
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    # Update the note
    annotation.note = annotation_update.note
    
    db.commit()
    db.refresh(annotation)
    
    return AnnotationResponse.from_annotation(annotation)


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an annotation
    
    Only the owner of the annotation can delete it.
    """
    annotation = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()
    
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    db.delete(annotation)
    db.commit()
    
    return None


@router.get("/text/{text_id}/summary")
async def get_text_annotations_summary(
    text_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get summary of annotations for a text
    
    Returns count of annotations and most annotated words.
    """
    from sqlalchemy import func
    
    # Verify text exists
    from src.models.text import Text
    text = db.query(Text).filter(Text.id == text_id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    
    # Get total count
    total = db.query(Annotation).filter(
        Annotation.user_id == current_user.id,
        Annotation.text_id == text_id
    ).count()
    
    # Get most annotated words
    most_annotated = db.query(
        Annotation.word,
        func.count(Annotation.id).label('count')
    ).filter(
        Annotation.user_id == current_user.id,
        Annotation.text_id == text_id
    ).group_by(Annotation.word).order_by(
        func.count(Annotation.id).desc()
    ).limit(10).all()
    
    return {
        "text_id": text_id,
        "total_annotations": total,
        "most_annotated_words": [
            {"word": word, "count": count}
            for word, count in most_annotated
        ]
    }

