"""Study tool models"""
from sqlalchemy import Column, Integer, String, ForeignKey, Text as TextType, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class StudentNote(Base):
    """User's personal notepad entry for a text"""
    
    __tablename__ = "student_notes"
    __table_args__ = (
        Index('idx_note_user_text', 'user_id', 'text_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text_id = Column(Integer, ForeignKey("texts.id"), nullable=True)  # Optional: can be global or text-specific
    content = Column(TextType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="notes")
    text = relationship("Text")
    
    def __repr__(self):
        return f"<StudentNote(id={self.id}, user_id={self.user_id})>"


class Highlight(Base):
    """User's text highlight"""
    
    __tablename__ = "highlights"
    __table_args__ = (
        Index('idx_highlight_user_text', 'user_id', 'text_id'),
        Index('idx_highlight_segment', 'user_id', 'segment_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text_id = Column(Integer, ForeignKey("texts.id"), nullable=False)
    segment_id = Column(Integer, ForeignKey("text_segments.id"), nullable=False)
    
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    selected_text = Column(String, nullable=False)
    color = Column(String, default="yellow")  # e.g., "yellow", "green", "pink"
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="highlights")
    text = relationship("Text")
    segment = relationship("TextSegment")
    
    def __repr__(self):
        return f"<Highlight(id={self.id}, user_id={self.user_id}, text='{self.selected_text[:20]}...')>"

