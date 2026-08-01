"""Tests for the two authentication modes enforced by get_current_user.

DEBUG=True means authentication is disabled entirely: every request resolves to
one shared dev user regardless of what credentials were sent. DEBUG=False means
a valid JWT is the only way in. Both halves are pinned here because the whole
auth design rests on them.
"""

from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPBearer
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import middleware.auth as auth_module
from database import Base, get_db
from middleware.auth import DEV_USER_EMAIL, get_current_user, get_or_create_dev_user
from models.user import User
from utils.security import create_access_token


@pytest.fixture
def ctx(monkeypatch):
    """Yields (make_client, session) where make_client(debug=...) builds an app.

    `security = HTTPBearer(auto_error=not DEBUG)` in middleware.auth is
    evaluated at import time, so DEBUG cannot be flipped after the fact for
    that object. Each client therefore overrides the scheme to match the mode
    under test, which is what the module would have built at that DEBUG value.
    """
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

        app = FastAPI()

        @app.get("/whoami")
        async def whoami(user: User = Depends(get_current_user)):
            return {"id": user.id, "email": user.email}

        app.dependency_overrides[get_db] = lambda: session
        # Mirror the module-level scheme for the mode being exercised.
        app.dependency_overrides[auth_module.security] = HTTPBearer(
            auto_error=not debug
        )
        return TestClient(app)

    yield make_client, session, real_user
    session.close()


def test_debug_mode_without_token_returns_dev_user(ctx):
    """DEBUG=True: no credentials at all still authenticates."""
    make_client, _, _ = ctx
    response = make_client(debug=True).get("/whoami")

    assert response.status_code == 200
    assert response.json()["email"] == DEV_USER_EMAIL


def test_debug_mode_ignores_valid_token_for_another_user(ctx):
    """DEBUG=True: a real token is deliberately ignored, not honoured.

    This is the "no authentication" semantic. Everyone collapses onto one
    identity, which is what makes annotations shared and open in debug.
    """
    make_client, _, real_user = ctx
    token = create_access_token(data={"sub": str(real_user.id)})

    response = make_client(debug=True).get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == DEV_USER_EMAIL
    assert response.json()["id"] != real_user.id


def test_debug_mode_reuses_single_dev_user(ctx):
    """DEBUG=True: repeated requests share one row rather than creating many."""
    make_client, session, _ = ctx
    client = make_client(debug=True)

    first = client.get("/whoami").json()
    second = client.get("/whoami").json()

    assert first["id"] == second["id"]
    assert session.query(User).filter(User.email == DEV_USER_EMAIL).count() == 1


def test_get_or_create_dev_user_is_idempotent(ctx):
    """Calling the helper twice returns the same row, not a duplicate."""
    _, session, _ = ctx

    first = get_or_create_dev_user(session)
    second = get_or_create_dev_user(session)

    assert first.id == second.id
    assert session.query(User).filter(User.email == DEV_USER_EMAIL).count() == 1


def test_production_mode_without_token_is_401(ctx):
    """DEBUG=False: a missing token is rejected."""
    make_client, _, _ = ctx
    assert make_client(debug=False).get("/whoami").status_code == 401


def test_production_mode_with_valid_token_returns_that_user(ctx):
    """DEBUG=False: a Google-issued token authenticates as its own user."""
    make_client, _, real_user = ctx
    token = create_access_token(data={"sub": str(real_user.id)})

    response = make_client(debug=False).get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "real@helios.local"


@pytest.mark.parametrize(
    "token,reason",
    [
        ("not-a-jwt", "malformed"),
        ("", "empty"),
    ],
)
def test_production_mode_rejects_bad_tokens(ctx, token, reason):
    """DEBUG=False: unparseable tokens are rejected."""
    make_client, _, _ = ctx
    response = make_client(debug=False).get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401, reason


def test_production_mode_rejects_expired_token(ctx):
    """DEBUG=False: an expired token no longer authenticates."""
    make_client, _, real_user = ctx
    token = create_access_token(
        data={"sub": str(real_user.id)}, expires_delta=timedelta(minutes=-5)
    )

    response = make_client(debug=False).get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_production_mode_rejects_non_integer_sub(ctx):
    """DEBUG=False: a `sub` that is not a user id is rejected."""
    make_client, _, _ = ctx
    token = create_access_token(data={"sub": "not-an-int"})

    response = make_client(debug=False).get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_production_mode_rejects_unknown_user_id(ctx):
    """DEBUG=False: a well-formed token for a deleted user is rejected."""
    make_client, _, _ = ctx
    token = create_access_token(data={"sub": "999999"})

    response = make_client(debug=False).get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
