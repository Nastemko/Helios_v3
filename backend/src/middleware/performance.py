"""Performance monitoring middleware"""

import logging
import time

from fastapi import Request

from config import settings

logger = logging.getLogger(__name__)


async def performance_middleware(request: Request, call_next):
    """
    Middleware to log request performance

    Logs warning if response time exceeds configured SLOW_REQUEST_THRESHOLD (default 0.5s)
    """
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time

    logger.info(f"{request.method} {request.url.path} " f"completed in {duration:.3f}s")

    # Alert if response time exceeds configured threshold
    if duration > settings.misc.SLOW_REQUEST_THRESHOLD:
        logger.warning(
            f"Slow request: {request.method} {request.url.path} "
            f"took {duration:.3f}s "
            f"(>{settings.misc.SLOW_REQUEST_THRESHOLD}s threshold)"
        )

    # Add response time header for debugging
    response.headers["X-Response-Time"] = f"{duration:.3f}s"

    return response
