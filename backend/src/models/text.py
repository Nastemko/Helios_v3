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
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import relationship

from database import Base


class Language(Enum):
    GRC = "grc"
    LAT = "lat"
    EN = "en"


class LiteraryText(Base):
    """Parent record for a literary work - language agnostic.

    One LiteraryText can have multiple LiteraryTextLangVersion children
    (original + translations).
    """

    __tablename__ = "literary_texts"
    __table_args__ = (Index("idx_literary_text_author_title", "author", "title"),)

    id = Column(Integer, primary_key=True)

    local_id = Column(String, unique=True, nullable=False, index=True)
    author = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)

    lang_versions = relationship(
        "LiteraryTextLangVersion",
        back_populates="literary_text",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<LiteraryText(local_id='{self.local_id}', author='{self.author}', title='{self.title}')>"


class LiteraryTextLangVersion(Base):
    """A specific language version of a literary text.

    This can be the original Greek/Latin text or a translation.
    Linked to parent LiteraryText for grouping all versions together.
    """

    __tablename__ = "literary_text_lang_versions"
    __table_args__ = (
        Index("idx_lang_version_local_id", "local_id"),
        Index("idx_lang_version_lang", "language"),
        Index("idx_lang_version_literary_text", "literary_text_id"),
    )

    id = Column(Integer, primary_key=True)

    literary_text_id = Column(
        Integer, ForeignKey("literary_texts.id"), index=True, nullable=False
    )
    local_id = Column(String, unique=True, nullable=False, index=True)
    language = Column(
        ENUM(Language, name="language_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    translator = Column(String, index=True)

    literary_text = relationship("LiteraryText", back_populates="lang_versions")
    segments = relationship(
        "TextSegment", back_populates="lang_version", cascade="all, delete-orphan"
    )
    annotations = relationship(
        "Annotation", back_populates="lang_version", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<LiteraryTextLangVersion(local_id='{self.local_id}', language='{self.language.value}')>"


class TextSegment(Base):
    """Individual segment of a literary text (line, paragraph, etc.)"""

    __tablename__ = "text_segments"
    __table_args__ = (
        Index("idx_segment_lang_version_id", "lang_version_id"),
        Index("idx_segment_reference", "lang_version_id", "reference"),
        Index("idx_segment_sequence", "lang_version_id", "sequence"),
    )

    id = Column(Integer, primary_key=True)
    lang_version_id = Column(
        Integer,
        ForeignKey("literary_text_lang_versions.id"),
        index=True,
        nullable=False,
    )
    book = Column(String, index=True)
    line = Column(String, index=True)
    sequence = Column(Integer, nullable=False, index=True)
    content = Column(TextType, nullable=False)
    reference = Column(String, nullable=False, index=True)

    lang_version = relationship("LiteraryTextLangVersion", back_populates="segments")
    annotations = relationship(
        "Annotation", back_populates="segment", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<TextSegment(lang_version_id={self.lang_version_id}, reference='{self.reference}')>"
