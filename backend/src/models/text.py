"""Text models"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, ForeignKey, Text as TextType, Index
from sqlalchemy.orm import relationship

from database import Base


class Text(Base):
    """Canonical text model (e.g., Homer's Iliad)"""
    
    __tablename__ = "texts"
    
    id = Column(Integer, primary_key=True, index=True)
    urn = Column(String, unique=True, nullable=False, index=True)  # e.g., urn:cts:greekLit:tlg0012.tlg001
    author = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    language = Column(String, nullable=False, index=True)  # 'grc', 'lat'
    is_fragment = Column(Boolean, default=False, index=True)
    text_metadata = Column(JSON)  # Additional metadata (editor, edition, etc.)
    
    # Relationships
    segments = relationship("TextSegment", back_populates="text", cascade="all, delete-orphan")
    annotations = relationship("Annotation", back_populates="text", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Text(urn='{self.urn}', author='{self.author}', title='{self.title}')>"


class TextSegment(Base):
    """Individual segment of a text (line, paragraph, etc.)"""
    
    __tablename__ = "text_segments"
    __table_args__ = (
        Index('idx_text_id', 'text_id'),
        Index('idx_text_reference', 'text_id', 'reference'),
        Index('idx_sequence', 'text_id', 'sequence'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    text_id = Column(Integer, ForeignKey("texts.id"), nullable=False)
    book = Column(String)  # Book number/name (e.g., "1")
    line = Column(String)  # Line number (e.g., "1")
    sequence = Column(Integer, nullable=False)  # For ordering
    content = Column(TextType, nullable=False)  # The actual Greek/Latin text
    reference = Column(String, nullable=False, index=True)  # e.g., "1.1" for book 1, line 1
    
    # Relationships
    text = relationship("Text", back_populates="segments")
    annotations = relationship("Annotation", back_populates="segment", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<TextSegment(text_id={self.text_id}, reference='{self.reference}')>"

