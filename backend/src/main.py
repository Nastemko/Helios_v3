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
from routers import (
    analysis,
    annotations,
    auth,
    inscriptions,
    texts,
    translate_assist,
)
from scripts.load_phi_inscriptions import initialize_phi_inscriptions
from scripts.populate_database import populate_on_startup
from scripts.populate_database_llm import llm_populate_on_startup
from services.ithaca_service.ithaca_service import (
    initialize_all_models,
    initialize_ithaca_service,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.misc.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Validate production configuration
try:
    settings.validate_production()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    raise

# Create FastAPI app
app = FastAPI(
    title=settings.misc.APP_NAME,
    debug=settings.misc.DEBUG,
    docs_url="/docs" if settings.misc.DEBUG else None,
    redoc_url="/redoc" if settings.misc.DEBUG else None,
)

# Add Session middleware (required for OAuth)
# Note: This must be added before other middleware that might use sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.auth.SECRET_KEY,
    max_age=3600,  # Session expires after 1 hour
    same_site="lax",
    https_only=not settings.misc.DEBUG,  # Secure in production, HTTP-safe in dev
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.misc.CORS_ORIGINS,
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
    logger.info(f"Starting {settings.misc.APP_NAME}")

    # Create database tables
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    # Populate database with Greek texts if not already populated
    logger.info("Checking for Greek text population...")

    try:
        stats = await populate_on_startup()
        if stats["inserted_versions"] > 0:
            logger.info(
                f"Populated database with {stats['inserted_versions']} text versions"
            )
        elif stats["skipped"] > 0:
            logger.info(f"Database already contains {stats['skipped']} texts")
    except Exception as e:
        logger.error(f"Error during text population: {e}")
        # Continue startup even if population fails

    # Run LLM-based population on failed files if OPENROUTER_API_KEY is set
    failures_file = Path(settings.assets.PERSEUS_DATA_DIR).parent / "lxml_failures.json"
    if failures_file.exists():
        from scripts.populate_database_llm import openrouter_config

        if openrouter_config.API_KEY and openrouter_config.API_KEY != "<your-key-here>":
            logger.info("Running LLM-based population on failed files...")
            try:
                llm_stats = await llm_populate_on_startup(failures_file=failures_file)
                if llm_stats["inserted_versions"] > 0:
                    logger.info(
                        f"LLM populated {llm_stats['inserted_versions']} versions "
                        f"({llm_stats['llm_calls']} LLM calls)"
                    )
            except Exception as e:
                logger.error(f"Error during LLM-based population: {e}")
                # Continue startup even if LLM population fails
        else:
            logger.info(
                "Skipping LLM population: OPENROUTER_API_KEY not set. "
                "Failed files are in %s",
                failures_file,
            )
    else:
        logger.info("No lxml failures file found, skipping LLM population")

    # Initialize PHI inscriptions
    logger.info("Initializing PHI inscriptions...")
    try:
        phi_stats = initialize_phi_inscriptions()
        logger.info("PHI inscription initialization complete")
    except Exception as e:
        logger.error(f"Error during PHI inscription initialization: {e}")
        # Continue startup even if PHI loading fails

    # Initialize Morphology service
    logger.info("Initializing CLTK morphology service...")
    from services.morphology import get_morphology_service

    morphology_service = get_morphology_service()
    logger.info(f"Morphology service initialized: {morphology_service.initialized}")

    # Initialize Ithaca service
    logger.info("Initializing Ithaca service")
    initialize_ithaca_service()

    # Initialize Ithaca inscription models (Greek and Latin)
    logger.info("Initializing Ithaca inscription models...")

    try:
        ithaca_results = initialize_all_models()
        for lang, success in ithaca_results.items():
            if success:
                logger.info(f"Ithaca {lang.title()} model initialized successfully")
            else:
                logger.warning(
                    f"Ithaca {lang.title()} model not available (files may not be present)"
                )
    except Exception as e:
        logger.error(f"Error initializing Ithaca models: {e}")
        # Continue startup even if Ithaca models fail to load

    logger.info(f"{settings.misc.APP_NAME} started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info(f"Shutting down {settings.misc.APP_NAME}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "app": settings.misc.APP_NAME}


app.include_router(texts.router)
app.include_router(auth.router)
app.include_router(annotations.router)
app.include_router(analysis.router)
app.include_router(inscriptions.router)
app.include_router(translate_assist.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.misc.DEBUG)
