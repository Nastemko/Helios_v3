"""User model"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    """User account model"""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    oauth_provider = Column(String, nullable=False)  # 'google', etc.
    oauth_id = Column(String, nullable=False)  # ID from OAuth provider
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    annotations = relationship("Annotation", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"

