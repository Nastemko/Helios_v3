"""PHI inscription models"""

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy import Text as TextType
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


class Inscription(Base):
    """PHI inscription model with structured and flexible metadata"""

    __tablename__ = "inscriptions"
    __table_args__ = (Index("idx_date_range", "date_min", "date_max"),)

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
