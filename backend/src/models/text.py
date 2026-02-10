"""Text models"""

from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Text as TextType
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import relationship

from database import Base


class TextSource(Enum):
    PHI = 0
    GreekLit = 1


class Language(Enum):
    GRC = "grc"  # Ancient Greek
    LAT = "lat"  # Latin
    EN = "en"  # English (for translations)


class TextMetadata(Base):
    """Language-agnostic metadata for texts"""

    __tablename__ = "text_metadata"
    __table_args__ = (
        # Composite index for common region + date queries
        Index("idx_region_date_combo", "region_main", "date_min", "date_max"),
    )

    id = Column(Integer, primary_key=True)

    # Postgres enum column for source/origin of the text.
    # Possible values: PHI, GreekLit
    source = Column(
        ENUM(TextSource, name="text_source_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    is_fragment = Column(Boolean, default=False, index=True)

    # Base local ID (without language suffix) - shared across all language versions
    local_id = Column(String, unique=True, nullable=False, index=True)

    # Extracted performance columns for fast querying
    region_main = Column(String, nullable=True, index=True)
    region_sub = Column(String, nullable=True, index=True)
    date_min = Column(Integer, nullable=True, index=True)
    date_max = Column(Integer, nullable=True, index=True)

    text_metadata = Column(JSONB)  # Merged metadata from all language versions

    # Relationships
    texts = relationship("Text", back_populates="metadata")

    def __repr__(self):
        return f"<TextMetadata(id={self.id}, source='{self.source}')>"


class Text(Base):
    """Text model for all languages (originals and translations)"""

    __tablename__ = "texts"
    __table_args__ = (
        Index("idx_author_title", "author", "title"),
        Index("idx_metadata_language", "metadata_id", "language"),
    )

    id = Column(Integer, primary_key=True, index=True, nullable=False)

    # Foreign key to language-agnostic metadata
    metadata_id = Column(
        Integer, ForeignKey("text_metadata.id"), index=True, nullable=False
    )

    # Language-specific fields
    author = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)
    translator = Column(
        String, index=True
    )  # NULL = original, "unknown" = unknown translator
    language = Column(
        ENUM(Language, name="language_enum", native_enum=True),
        nullable=False,
        index=True,
    )

    # Relationships
    metadata = relationship("TextMetadata", back_populates="texts")
    segments = relationship(
        "TextSegment", back_populates="text", cascade="all, delete-orphan"
    )
    annotations = relationship(
        "Annotation", back_populates="text", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Text(local_id='{self.local_id}', language='{self.language.value}', author='{self.author}', title='{self.title}')>"


class TextSegment(Base):
    """Individual segment of a text (line, paragraph, etc.)"""

    __tablename__ = "text_segments"
    __table_args__ = (
        Index("idx_text_id", "text_id"),
        Index("idx_text_reference", "text_id", "reference"),
        Index("idx_sequence", "text_id", "sequence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    text_id = Column(Integer, ForeignKey("texts.id"), index=True, nullable=False)
    book = Column(String, index=True)  # Book number/name (e.g., "1")
    line = Column(String, index=True)  # Line number (e.g., "1")
    sequence = Column(Integer, nullable=False, index=True)  # For ordering
    content = Column(TextType, nullable=False)  # The actual Greek/Latin text
    reference = Column(
        String, nullable=False, index=True
    )  # e.g., "1.1" for book 1, line 1

    # Relationships
    text = relationship("Text", back_populates="segments")
    annotations = relationship(
        "Annotation", back_populates="segment", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<TextSegment(text_id={self.text_id}, reference='{self.reference}')>"
