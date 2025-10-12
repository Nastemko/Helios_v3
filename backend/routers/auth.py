"""Authentication API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel

from config import settings
from database import get_db
from models.user import User
from utils.security import create_access_token
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Initialize OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)


class UserResponse(BaseModel):
    """User response model"""
    id: int
    email: str
    oauth_provider: str
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.get("/login/google")
async def login_google(request: Request):
    """
    Redirect to Google OAuth login
    
    This endpoint redirects the user to Google's OAuth consent page.
    """
    # Build redirect URI
    redirect_uri = request.url_for('auth_google_callback')
    
    # Redirect to Google OAuth
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback/google")
async def auth_google_callback(
    request: Request,
    db: Session = Depends(get_db)
):
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
        user_info = token.get('userinfo')
        if not user_info:
            # Fallback to calling userinfo endpoint
            resp = await oauth.google.get('userinfo', token=token)
            user_info = resp.json()
        
        email = user_info.get('email')
        oauth_id = user_info.get('sub')  # Google's user ID
        
        if not email or not oauth_id:
            raise HTTPException(status_code=400, detail="Could not get user info from Google")
        
        # Find or create user in database
        user = db.query(User).filter(
            User.oauth_provider == 'google',
            User.oauth_id == oauth_id
        ).first()
        
        if not user:
            # Create new user
            user = User(
                email=email,
                oauth_provider='google',
                oauth_id=oauth_id
            )
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
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Generated token for user {user.id} ({user.email}), length {len(access_token)}")
        logger.info(f"Token preview: {access_token[:80]}...")
        
        # Redirect to frontend with token
        # Frontend should extract token from URL and store it
        frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
        redirect_url = f"{frontend_url}/?token={access_token}"
        
        logger.info(f"Redirecting to: {redirect_url[:80]}...")
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        # Log error and redirect to frontend with error
        print(f"OAuth error: {e}")
        frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
        return RedirectResponse(url=f"{frontend_url}/?error=auth_failed")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's information
    
    Requires valid JWT token in Authorization header.
    """
    return UserResponse.from_orm(current_user)


@router.post("/logout")
async def logout():
    """
    Logout endpoint
    
    Since we use JWT tokens (stateless), logout is handled client-side
    by removing the token from storage. This endpoint just confirms the action.
    """
    return {"message": "Logged out successfully"}


@router.get("/status")
async def auth_status(request: Request, db: Session = Depends(get_db)):
    """
    Check authentication status
    
    Returns user info if authenticated, otherwise returns null.
    """
    from middleware.auth import get_current_user_optional
    
    try:
        # Try to get current user without raising error
        from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
        from typing import Optional
        
        security = HTTPBearer(auto_error=False)
        credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
        
        if credentials:
            from utils.security import verify_token
            payload = verify_token(credentials.credentials)
            
            if payload:
                user_id_str = payload.get("sub")
                if user_id_str:
                    try:
                        user_id = int(user_id_str)
                    except (ValueError, TypeError):
                        return {"authenticated": False, "user": None}
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        return {
                            "authenticated": True,
                            "user": UserResponse.from_orm(user)
                        }
        
        return {"authenticated": False, "user": None}
        
    except Exception:
        return {"authenticated": False, "user": None}

