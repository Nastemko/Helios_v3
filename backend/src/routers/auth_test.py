"""Tests for the /api/auth endpoints.

Two invariants matter here: Google OAuth is the only credential path in
production (so dev-login must not exist), and /status must report the same
thing get_current_user enforces, including under DEBUG.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from middleware.auth import DEV_USER_EMAIL
from models.user import User
from routers.auth import router
from utils.security import create_access_token


@pytest.fixture
def ctx(monkeypatch):
    """Yields (make_client, session, real_user); make_client(debug=...) per mode."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    real_user = User(
        email="real@helios.local", oauth_provider="google", oauth_id="google-123"
    )
    session.add(real_user)
    session.commit()

    def make_client(debug: bool) -> TestClient:
        monkeypatch.setattr("middleware.auth.settings.misc.DEBUG", debug)
        monkeypatch.setattr("routers.auth.settings.misc.DEBUG", debug)

        app = FastAPI()
        app.include_router(router)  # router declares prefix="/api/auth"
        app.dependency_overrides[get_db] = lambda: session
        return TestClient(app)

    yield make_client, session, real_user
    session.close()


def test_dev_login_endpoint_no_longer_exists(ctx):
    """The only non-Google credential path is gone, in either mode."""
    make_client, _, _ = ctx

    assert make_client(debug=True).post("/api/auth/dev-login").status_code == 404
    assert make_client(debug=False).post("/api/auth/dev-login").status_code == 404


def test_status_in_debug_reports_shared_dev_user(ctx):
    """DEBUG=True: /status agrees with get_current_user that auth is off.

    It previously hand-rolled token checks and reported authenticated=false
    while every protected endpoint served the dev user.
    """
    make_client, _, _ = ctx
    response = make_client(debug=True).get("/api/auth/status")

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == DEV_USER_EMAIL


def test_status_without_token_in_production_is_unauthenticated(ctx):
    """DEBUG=False: no token means not authenticated, and no exception."""
    make_client, _, _ = ctx
    response = make_client(debug=False).get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


def test_status_with_valid_token_in_production(ctx):
    """DEBUG=False: a valid token reports that user."""
    make_client, _, real_user = ctx
    token = create_access_token(data={"sub": str(real_user.id)})

    response = make_client(debug=False).get(
        "/api/auth/status", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "real@helios.local"


def test_status_with_bad_token_in_production_does_not_raise(ctx):
    """DEBUG=False: a garbage token yields a soft negative, not a 401."""
    make_client, _, _ = ctx
    response = make_client(debug=False).get(
        "/api/auth/status", headers={"Authorization": "Bearer garbage"}
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


def test_me_without_token_in_production_is_401(ctx):
    """DEBUG=False: /me requires a real token."""
    make_client, _, _ = ctx

    response = make_client(debug=False).get("/api/auth/me")
    assert response.status_code in (401, 403)


def test_me_in_debug_returns_dev_user(ctx):
    """DEBUG=True: /me works with no credentials and returns the shared user."""
    make_client, _, _ = ctx
    response = make_client(debug=True).get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == DEV_USER_EMAIL


def test_login_google_is_the_only_login_route(ctx):
    """Route table exposes exactly one way to obtain a session: Google."""
    paths = {route.path for route in router.routes}

    assert "/api/auth/login/google" in paths
    assert "/api/auth/callback/google" in paths
    assert not any("dev" in path for path in paths)
