"""Text models"""

from enum import Enum

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String
from sqlalchemy import Text as TextType
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import relationship

from database import Base


class TextSource(Enum):
    PHI = 0
    GreekLit = 1


class Text(Base):
    """Canonical text model (e.g., Homer's Iliad)"""

    __tablename__ = "texts"
    __table_args__ = (
        Index("idx_author_title", "author", "title"),
        # Composite index for common region + date queries
        Index("idx_region_date_combo", "region_main", "date_min", "date_max"),
    )

    id = Column(Integer, primary_key=True, index=True, nullable=False)

    local_id = Column(String, unique=True, nullable=False, index=True)

    # Postgres enum column for source/origin of the text.
    # Possible values: PHI, GreekLit
    source = Column(
        ENUM(TextSource, name="text_source_enum", native_enum=True),
        nullable=False,
        index=True,
    )

    author = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False, index=True)  # 'grc', 'lat'
    is_fragment = Column(Boolean, default=False, index=True)

    # Extracted performance columns for fast querying
    region_main = Column(String, nullable=True, index=True)
    region_sub = Column(String, nullable=True, index=True)
    date_min = Column(Integer, nullable=True, index=True)
    date_max = Column(Integer, nullable=True, index=True)

    text_metadata = Column(JSONB)  # Additional metadata (editor, edition, etc.)

    # Relationships
    segments = relationship(
        "TextSegment", back_populates="text", cascade="all, delete-orphan"
    )
    annotations = relationship(
        "Annotation", back_populates="text", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Text(local_id='{self.local_id}', source='{self.source}', author='{self.author}', title='{self.title}')>"


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
    book = Column(String)  # Book number/name (e.g., "1")
    line = Column(String)  # Line number (e.g., "1")
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
