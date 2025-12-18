"""API endpoints for study tools (notes and highlights)"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db
from models.user import User
from models.study import StudentNote, Highlight
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/study", tags=["study"])


# --- Schemas ---

class NoteBase(BaseModel):
    content: str
    text_id: Optional[int] = None

class NoteCreate(NoteBase):
    pass

class NoteUpdate(BaseModel):
    content: str

class NoteResponse(NoteBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HighlightBase(BaseModel):
    text_id: int
    segment_id: int
    start_offset: int
    end_offset: int
    selected_text: str
    color: str = "yellow"

class HighlightCreate(HighlightBase):
    pass

class HighlightResponse(HighlightBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Note Endpoints ---

@router.post("/notes", response_model=NoteResponse)
async def create_note(
    note: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new note"""
    db_note = StudentNote(
        user_id=current_user.id,
        text_id=note.text_id,
        content=note.content
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

@router.get("/notes", response_model=List[NoteResponse])
async def get_notes(
    text_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's notes, optionally filtered by text_id"""
    query = db.query(StudentNote).filter(StudentNote.user_id == current_user.id)
    
    if text_id:
        query = query.filter(StudentNote.text_id == text_id)
    
    return query.order_by(StudentNote.updated_at.desc()).all()

@router.put("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a note"""
    db_note = db.query(StudentNote).filter(
        StudentNote.id == note_id,
        StudentNote.user_id == current_user.id
    ).first()
    
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    db_note.content = note.content
    db.commit()
    db.refresh(db_note)
    return db_note

@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a note"""
    db_note = db.query(StudentNote).filter(
        StudentNote.id == note_id,
        StudentNote.user_id == current_user.id
    ).first()
    
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    db.delete(db_note)
    db.commit()
    return {"message": "Note deleted"}


# --- Highlight Endpoints ---

@router.post("/highlights", response_model=HighlightResponse)
async def create_highlight(
    highlight: HighlightCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new highlight"""
    db_highlight = Highlight(
        user_id=current_user.id,
        **highlight.model_dump()
    )
    db.add(db_highlight)
    db.commit()
    db.refresh(db_highlight)
    return db_highlight

@router.get("/highlights", response_model=List[HighlightResponse])
async def get_highlights(
    text_id: Optional[int] = None,
    segment_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's highlights"""
    query = db.query(Highlight).filter(Highlight.user_id == current_user.id)
    
    if text_id:
        query = query.filter(Highlight.text_id == text_id)
    if segment_id:
        query = query.filter(Highlight.segment_id == segment_id)
        
    return query.all()

@router.delete("/highlights/{highlight_id}")
async def delete_highlight(
    highlight_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a highlight"""
    db_highlight = db.query(Highlight).filter(
        Highlight.id == highlight_id,
        Highlight.user_id == current_user.id
    ).first()
    
    if not db_highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    db.delete(db_highlight)
    db.commit()
    return {"message": "Highlight deleted"}

