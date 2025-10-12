"""Annotation model"""
from sqlalchemy import Column, Integer, String, ForeignKey, Text as TextType, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class Annotation(Base):
    """User annotation on a word or phrase"""
    
    __tablename__ = "annotations"
    __table_args__ = (
        Index('idx_user_text', 'user_id', 'text_id'),
        Index('idx_user_segment', 'user_id', 'segment_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text_id = Column(Integer, ForeignKey("texts.id"), nullable=False)
    segment_id = Column(Integer, ForeignKey("text_segments.id"), nullable=False)
    word = Column(String, nullable=False)  # The specific word being annotated
    note = Column(TextType, nullable=False)  # User's note/translation
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="annotations")
    text = relationship("Text", back_populates="annotations")
    segment = relationship("TextSegment", back_populates="annotations")
    
    def __repr__(self):
        return f"<Annotation(id={self.id}, user_id={self.user_id}, word='{self.word}')>"

