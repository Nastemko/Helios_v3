"""Authentication middleware and dependencies"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.user import User
from utils.security import verify_token

# In dev mode, don't auto-error on missing credentials
security = HTTPBearer(auto_error=not settings.DEBUG)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency to get the currently authenticated user

    Args:
        credentials: HTTP Bearer token from request
        db: Database session

    Returns:
        Authenticated User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    import logging

    logger = logging.getLogger(__name__)

    # DEV MODE: Bypass authentication if DEBUG is true and no credentials are provided
    if settings.DEBUG:
        logger.info("DEV MODE: No credentials provided, using dev user")
        dev_user = db.query(User).filter(User.email == "dev@helios.local").first()
        if not dev_user:
            dev_user = User(
                email="dev@helios.local", oauth_provider="dev", oauth_id="dev_id"
            )
            db.add(dev_user)
            db.commit()
            db.refresh(dev_user)
            logger.info("DEV MODE: Created dev user")
        return dev_user

    if not credentials:
        raise credentials_exception

    token = credentials.credentials
    logger.info(
        f"Received token (length {len(token)}): {token[:50]}..."
        if len(token) > 50
        else f"Received token: {token}"
    )

    payload = verify_token(token)
    logger.debug(f"Token payload: {payload}")

    if payload is None:
        logger.warning("Token verification failed - payload is None")
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        logger.warning("No user_id (sub) in token payload")
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        logger.warning(f"Invalid user_id in token: {user_id_str}")
        raise credentials_exception

    logger.debug(f"Looking up user with ID: {user_id}")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        logger.warning(f"User with ID {user_id} not found in database")
        raise credentials_exception

    logger.debug(f"Successfully authenticated user: {user.email}")
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Dependency to optionally get the current user (doesn't raise error if not authenticated)

    Args:
        credentials: Optional HTTP Bearer token from request
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        return None

    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user
