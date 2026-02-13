"""Annotation model"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Text as TextType
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Annotation(Base):
    """User annotation on a word or phrase"""

    __tablename__ = "annotations"
    __table_args__ = (
        Index("idx_user_text", "user_id", "text_id"),
        Index("idx_user_segment", "user_id", "segment_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    text_id = Column(
        Integer, ForeignKey("literary_texts.id"), index=True, nullable=False
    )
    segment_id = Column(
        Integer, ForeignKey("text_segments.id"), index=True, nullable=False
    )
    word = Column(
        String, index=True, nullable=False
    )  # The specific word being annotated
    note = Column(TextType, nullable=False)  # User's note/translation
    created_at = Column(DateTime(timezone=True), index=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="annotations")
    text = relationship("LiteraryText", back_populates="annotations")
    segment = relationship("TextSegment", back_populates="annotations")

    def __repr__(self):
        return f"<Annotation(id={self.id}, user_id={self.user_id}, word='{self.word}')>"
