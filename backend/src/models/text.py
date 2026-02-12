"""Text models for Greek literary texts"""

from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy import Text as TextType
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import relationship

from database import Base


class Language(Enum):
    GRC = "grc"  # Ancient Greek
    LAT = "lat"  # Latin
    EN = "en"  # English (for translations)


class LiteraryText(Base):
    """GreekLit literary text model for originals and translations"""

    __tablename__ = "literary_texts"
    __table_args__ = (
        Index("idx_author_title", "author", "title"),
        Index("idx_local_id_language", "local_id", "language"),
    )

    id = Column(Integer, primary_key=True)

    # Core identification
    local_id = Column(String, unique=True, nullable=False, index=True)  # Base ID
    author = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)

    # Language and translation data
    language = Column(
        ENUM(Language, name="language_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    translator = Column(
        String, index=True
    )  # NULL = original, "unknown" = unknown translator
    is_translation = Column(Boolean, default=False, index=True)

    # Foreign key to shared metadata
    metadata_id = Column(
        Integer, ForeignKey("text_metadata.id"), index=True, nullable=False
    )

    # Relationships
    text_metadata = relationship("TextMetadata", back_populates="texts")
    segments = relationship(
        "TextSegment", back_populates="text", cascade="all, delete-orphan"
    )
    annotations = relationship(
        "Annotation", back_populates="text", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<LiteraryText(local_id='{self.local_id}', language='{self.language.value}', author='{self.author}', title='{self.title}')>"


class TextMetadata(Base):
    """Language-agnostic metadata for literary texts"""

    __tablename__ = "text_metadata"

    id = Column(Integer, primary_key=True)
    local_id = Column(
        String, unique=True, nullable=False, index=True
    )  # Base ID for sharing
    metadata_content = Column(JSONB)  # Merged metadata from all language versions

    # Relationships
    texts = relationship("LiteraryText", back_populates="metadata")

    def __repr__(self):
        return f"<TextMetadata(local_id='{self.local_id}')>"


class TextSegment(Base):
    """Individual segment of a literary text (line, paragraph, etc.)"""

    __tablename__ = "text_segments"
    __table_args__ = (
        Index("idx_text_id", "text_id"),
        Index("idx_text_reference", "text_id", "reference"),
        Index("idx_sequence", "text_id", "sequence"),
    )

    id = Column(Integer, primary_key=True)
    text_id = Column(
        Integer, ForeignKey("literary_texts.id"), index=True, nullable=False
    )
    book = Column(String, index=True)  # Book number/name (e.g., "1")
    line = Column(String, index=True)  # Line number (e.g., "1")
    sequence = Column(Integer, nullable=False, index=True)  # For ordering
    content = Column(TextType, nullable=False)  # The actual Greek/Latin text
    reference = Column(
        String, nullable=False, index=True
    )  # e.g., "1.1" for book 1, line 1

    # Relationships
    text = relationship("LiteraryText", back_populates="segments")
    annotations = relationship(
        "Annotation", back_populates="segment", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<TextSegment(text_id={self.text_id}, reference='{self.reference}')>"
