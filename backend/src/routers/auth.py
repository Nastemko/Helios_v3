"""Authentication API endpoints"""

import logging

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.auth import (
    get_current_user,
    get_or_create_dev_user,
    resolve_user_from_token,
)
from models.user import User
from utils.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Soft bearer check for /status: never auto-errors on a missing token.
optional_security = HTTPBearer(auto_error=False)

# Initialize OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.auth.GOOGLE_CLIENT_ID,
    client_secret=settings.auth.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


class UserResponse(BaseModel):
    """User response model"""

    id: int
    email: str
    oauth_provider: str

    model_config = {"from_attributes": True}


@router.get("/login/google")
async def login_google(request: Request):
    """
    Redirect to Google OAuth login

    This endpoint redirects the user to Google's OAuth consent page.
    """
    # Build redirect URI
    redirect_uri = request.url_for("auth_google_callback")

    # Redirect to Google OAuth
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback/google")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    """
    Handle Google OAuth callback

    This endpoint is called by Google after user authorizes.
    It exchanges the authorization code for an access token,
    retrieves user info, creates/updates the user in the database,
    and redirects back to the frontend with a JWT token.
    """
    try:
        # Get access token from Google
        token = await oauth.google.authorize_access_token(request)

        # Get user info from Google
        user_info = token.get("userinfo")
        if not user_info:
            # Fallback to calling userinfo endpoint
            resp = await oauth.google.get("userinfo", token=token)
            user_info = resp.json()

        email = user_info.get("email")
        oauth_id = user_info.get("sub")  # Google's user ID

        if not email or not oauth_id:
            raise HTTPException(
                status_code=400, detail="Could not get user info from Google"
            )

        # Find or create user in database
        user = (
            db.query(User)
            .filter(User.oauth_provider == "google", User.oauth_id == oauth_id)
            .first()
        )

        if not user:
            # Create new user
            user = User(email=email, oauth_provider="google", oauth_id=oauth_id)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update email if changed
            if user.email != email:
                user.email = email
                db.commit()

        # Generate JWT token
        access_token = create_access_token(data={"sub": str(user.id)})

        logger.info(f"Generated token for user {user.id} ({user.email})")

        # Redirect to frontend with token in fragment (not query param)
        # Fragments are never sent to servers, preventing token leakage via referrer/logs
        frontend_url = (
            settings.misc.CORS_ORIGINS[0]
            if settings.misc.CORS_ORIGINS
            else "http://localhost:3000"
        )
        redirect_url = f"{frontend_url}/#token={access_token}"

        logger.info(f"Redirecting user {user.id} to frontend after OAuth")
        return RedirectResponse(url=redirect_url)

    except HTTPException:
        # Deliberate rejections (e.g. missing user info) keep their status code
        # rather than being flattened into a generic redirect.
        raise
    except Exception:
        logger.exception("Google OAuth callback failed")
        frontend_url = (
            settings.misc.CORS_ORIGINS[0]
            if settings.misc.CORS_ORIGINS
            else "http://localhost:3000"
        )
        return RedirectResponse(url=f"{frontend_url}/?error=auth_failed")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's information

    Requires valid JWT token in Authorization header.
    """
    return UserResponse.model_validate(current_user)


@router.post("/logout")
async def logout():
    """
    Logout endpoint

    Since we use JWT tokens (stateless), logout is handled client-side
    by removing the token from storage. This endpoint just confirms the action.
    """
    return {"message": "Logged out successfully"}


@router.get("/status")
async def auth_status(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: Session = Depends(get_db),
):
    """
    Check authentication status

    Never raises. Mirrors the semantics of get_current_user: when DEBUG is on
    authentication is disabled and the shared dev user is always reported, so
    the frontend can treat this as the single source of truth for which mode
    the backend is running in.
    """
    if settings.misc.DEBUG:
        user = get_or_create_dev_user(db)
        return {"authenticated": True, "user": UserResponse.model_validate(user)}

    if credentials:
        user = resolve_user_from_token(credentials.credentials, db)
        if user:
            return {"authenticated": True, "user": UserResponse.model_validate(user)}

    return {"authenticated": False, "user": None}
