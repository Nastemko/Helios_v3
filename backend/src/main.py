"""Main FastAPI application"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from config import settings
from database import Base, engine
from middleware.performance import performance_middleware

# Import and include routers
from routers import aeneas, analysis, annotations, auth, texts, tutor

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add Session middleware (required for OAuth)
# Note: This must be added before other middleware that might use sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=3600,  # Session expires after 1 hour
    same_site="lax",
    https_only=False,  # Set to True in production with HTTPS
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add performance monitoring middleware
app.middleware("http")(performance_middleware)


# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info(f"Starting {settings.APP_NAME}")

    # Create database tables
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    # Populate database with Greek texts if not already populated
    logger.info("Checking for Greek text population...")
    from scripts.populate_on_startup import populate_on_startup

    try:
        stats = await populate_on_startup()
        if stats["inserted"] > 0:
            logger.info(f"Populated database with {stats['inserted']} Greek texts")
        elif stats["skipped"] > 0:
            logger.info(f"Database already contains {stats['skipped']} texts")
    except Exception as e:
        logger.error(f"Error during text population: {e}")
        # Continue startup even if population fails

    # Initialize Morphology service
    logger.info("Initializing CLTK morphology service...")
    from services.morphology import get_morphology_service

    morphology_service = get_morphology_service()
    logger.info(f"Morphology service initialized: {morphology_service.initialized}")

    # Initialize Aeneas service
    models_dir = Path(settings.MODELS_DIR)
    logger.info(f"Initializing Aeneas service with models from {models_dir}")

    from services.aeneas_service import initialize_aeneas_service

    initialize_aeneas_service(models_dir)

    logger.info(f"{settings.APP_NAME} started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info(f"Shutting down {settings.APP_NAME}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "app": settings.APP_NAME}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Helios API",
        "docs": "/docs" if settings.DEBUG else "Documentation disabled in production",
        "version": "1.0.0",
    }


app.include_router(texts.router)
app.include_router(auth.router)
app.include_router(annotations.router)
app.include_router(analysis.router)
app.include_router(aeneas.router)
app.include_router(tutor.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
