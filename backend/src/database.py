"""Database configuration and session management"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from config import settings


def _db_url() -> str:
    db_set = settings.database
    return f"postgresql://{db_set.USER}:{db_set.PASSWORD}@{db_set.HOST}:{db_set.PORT}/{db_set.DB}"


@lru_cache(maxsize=1)
def _get_engine() -> Engine:
    engine_kwargs = {
        "poolclass": QueuePool,
        "pool_size": 20,
        "max_overflow": 40,
        "pool_timeout": 30,
        "pool_recycle": 3600,
        "echo": settings.misc.DEBUG,
        "connect_args": {
            "options": "-c timezone=utc",
            "connect_timeout": 10,
        },
    }
    engine = create_engine(_db_url(), **engine_kwargs)
    return engine


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())

# Base class for models
Base = declarative_base()

engine = _get_engine()


def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
