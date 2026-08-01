"""Security utilities for JWT tokens"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

import jwt
from jwt.exceptions import PyJWTError

from config import settings

logger = logging.getLogger(__name__)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token

    Args:
        data: Dictionary of data to encode in the token
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.auth.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.auth.SECRET_KEY, algorithm=settings.auth.ALGORITHM
    )

    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token, settings.auth.SECRET_KEY, algorithms=[settings.auth.ALGORITHM]
        )
        return payload
    except PyJWTError as e:
        logger.error(f"JWT verification failed: {type(e).__name__}: {str(e)}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error during token verification: {type(e).__name__}: {str(e)}"
        )
        return None
