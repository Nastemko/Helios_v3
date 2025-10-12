"""Performance monitoring middleware"""
import time
import logging
from fastapi import Request

logger = logging.getLogger(__name__)


async def performance_middleware(request: Request, call_next):
    """
    Middleware to log request performance
    
    Logs warning if response time exceeds 500ms threshold
    """
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} "
        f"completed in {duration:.3f}s"
    )
    
    # Alert if response time exceeds PRD requirement of 500ms
    if duration > 0.5:
        logger.warning(
            f"Slow request: {request.method} {request.url.path} "
            f"took {duration:.3f}s (>500ms threshold)"
        )
    
    # Add response time header for debugging
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    return response

