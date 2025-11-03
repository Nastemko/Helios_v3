"""Database configuration and session management"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from config import settings

# Determine if using PostgreSQL
is_postgres = settings.DATABASE_URL.startswith("postgresql")

# Create database engine with connection pooling
engine_kwargs = {
    "poolclass": QueuePool,
    "pool_size": 20,
    "max_overflow": 40,
    "pool_timeout": 30,
    "pool_recycle": 3600,
    "echo": settings.DEBUG,
}

# Add PostgreSQL-specific connection args
if is_postgres:
    engine_kwargs["connect_args"] = {
        "options": "-c timezone=utc",
        "connect_timeout": 10,
    }

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

