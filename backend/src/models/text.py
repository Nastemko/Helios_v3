"""Text models"""

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


class Inscription(Base):
    """PHI inscription model with structured and flexible metadata"""

    __tablename__ = "inscriptions"
    __table_args__ = (
        Index("idx_region_main", "region_main"),
        Index("idx_region_sub", "region_sub"),
        Index("idx_date_range", "date_min", "date_max"),
        Index("idx_phi_id", "phi_id"),
    )

    id = Column(Integer, primary_key=True)

    # Core identification
    phi_id = Column(Integer, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)

    # Extracted PHI fields (NOT duplicated in JSONB)
    region_main = Column(String, nullable=True, index=True)
    region_sub = Column(String, nullable=True, index=True)
    date_min = Column(Integer, nullable=True, index=True)  # BC negative, AD positive
    date_max = Column(Integer, nullable=True, index=True)  # BC negative, AD positive
    date_str = Column(String)  # Human-readable date (e.g., "c. 450 BCE")
    date_circa = Column(Boolean, default=False)

    # Remaining PHI metadata (non-extracted fields only)
    metadata_raw = Column(JSONB)  # Original PHI JSON minus extracted fields

    # Relationships
    segments = relationship(
        "InscriptionSegment", back_populates="inscription", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Inscription(phi_id={self.phi_id}, title='{self.title}')>"


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

    # Work classification
    is_fragment = Column(Boolean, default=False, index=True)

    # Foreign key to shared metadata
    metadata_id = Column(
        Integer, ForeignKey("text_metadata.id"), index=True, nullable=False
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
        return f"<LiteraryText(local_id='{self.local_id}', language='{self.language.value}', author='{self.author}', title='{self.title}')>"


class TextMetadata(Base):
    """Language-agnostic metadata for literary texts"""

    __tablename__ = "text_metadata"

    id = Column(Integer, primary_key=True)
    local_id = Column(
        String, unique=True, nullable=False, index=True
    )  # Base ID for sharing
    text_metadata = Column(JSONB)  # Merged metadata from all language versions

    # Relationships
    texts = relationship("LiteraryText", back_populates="metadata")

    def __repr__(self):
        return f"<TextMetadata(local_id='{self.local_id}')>"


class InscriptionSegment(Base):
    """Individual segment of an inscription"""

    __tablename__ = "inscription_segments"
    __table_args__ = (Index("idx_inscription_sequence", "inscription_id", "sequence"),)

    id = Column(Integer, primary_key=True)
    inscription_id = Column(
        Integer, ForeignKey("inscriptions.id"), index=True, nullable=False
    )
    sequence = Column(Integer, nullable=False)
    content = Column(TextType, nullable=False)  # The actual inscription text

    # Relationships
    inscription = relationship("Inscription", back_populates="segments")

    def __repr__(self):
        return f"<InscriptionSegment(inscription_id={self.inscription_id}, sequence={self.sequence})>"


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
