"""Authentication middleware and dependencies"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.user import User
from utils.security import verify_token

logger = logging.getLogger(__name__)

# In dev mode, don't auto-error on missing credentials
security = HTTPBearer(auto_error=not settings.misc.DEBUG)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# The single shared identity used when DEBUG is on. See get_or_create_dev_user.
DEV_USER_EMAIL = "dev@helios.local"
DEV_USER_OAUTH_PROVIDER = "dev"
DEV_USER_OAUTH_ID = "dev_id"


def get_or_create_dev_user(db: Session) -> User:
    """
    Get (or create) the single shared user used when DEBUG is on.

    When DEBUG is true authentication is disabled entirely and every request
    resolves to this one user, which makes annotations shared and open.

    Args:
        db: Database session

    Returns:
        The shared dev User object
    """
    dev_user = db.query(User).filter(User.email == DEV_USER_EMAIL).first()
    if dev_user:
        return dev_user

    dev_user = User(
        email=DEV_USER_EMAIL,
        oauth_provider=DEV_USER_OAUTH_PROVIDER,
        oauth_id=DEV_USER_OAUTH_ID,
    )
    db.add(dev_user)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request won the race to insert; use the row it created.
        db.rollback()
        return db.query(User).filter(User.email == DEV_USER_EMAIL).one()

    db.refresh(dev_user)
    logger.info(f"DEBUG=True: created shared dev user '{DEV_USER_EMAIL}'")
    return dev_user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency to get the currently authenticated user

    When DEBUG is true, authentication is disabled entirely: any supplied
    credentials are deliberately ignored and every request resolves to the
    shared dev user. When DEBUG is false, a valid Google-issued JWT is the
    only way in.

    Args:
        credentials: HTTP Bearer token from request
        db: Database session

    Returns:
        Authenticated User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Authentication is disabled in debug mode. Any credentials that were sent
    # are intentionally ignored so every caller shares one identity.
    if settings.misc.DEBUG:
        logger.info("DEBUG=True: authentication disabled, using shared dev user")
        return get_or_create_dev_user(db)

    # Production mode: require valid credentials
    if not credentials:
        raise credentials_exception

    token = credentials.credentials

    payload = verify_token(token)

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


def resolve_user_from_token(token: str, db: Session) -> User | None:
    """
    Resolve a user from a bearer token without raising.

    Used by soft-check endpoints such as GET /api/auth/status.

    Args:
        token: JWT token string
        db: Database session

    Returns:
        User object if the token is valid and the user exists, None otherwise
    """
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

    return db.query(User).filter(User.id == user_id).first()
