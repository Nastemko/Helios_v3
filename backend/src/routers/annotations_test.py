"""Tests for the /api/annotations update endpoint.

Covers PUT /api/annotations/{id}, which a bug report claimed did not exist, and
the ownership rule that makes another user's annotation indistinguishable from a
missing one.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from middleware.auth import get_current_user
from models.annotation import Annotation
from models.text import Language, LiteraryText, LiteraryTextLangVersion, TextSegment
from models.user import User
from routers.annotations import router


@pytest.fixture
def ctx():
    """App seeded with two users, each owning one annotation on the same word.

    Yields (TestClient, session, ids). `get_current_user` is overridden rather
    than driven by DEBUG: middleware.auth bypasses auth entirely when DEBUG is
    true and returns a single shared dev user, which would make the
    cross-user test pass for the wrong reason.
    """
    # StaticPool + check_same_thread=False: TestClient serves requests on a
    # separate thread, and a default SQLite connection is bound to its creator.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            LiteraryText.__table__,
            LiteraryTextLangVersion.__table__,
            TextSegment.__table__,
            Annotation.__table__,
        ],
    )
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    owner = User(email="owner@helios.local", oauth_provider="dev", oauth_id="owner")
    other = User(email="other@helios.local", oauth_provider="dev", oauth_id="other")
    work = LiteraryText(local_id="tlg0012.tlg001")
    session.add_all([owner, other, work])
    session.flush()

    version = LiteraryTextLangVersion(
        local_id="tlg0012.tlg001.perseus-grc1",
        literary_text_id=work.id,
        language=Language.GRC,
        author="Ὅμηρος",
        title="Ἰλιάς",
    )
    session.add(version)
    session.flush()

    segment = TextSegment(
        lang_version_id=version.id,
        sequence=1,
        content="μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        reference="1.1",
    )
    session.add(segment)
    session.flush()

    owned = Annotation(
        user_id=owner.id,
        lang_version_id=version.id,
        segment_id=segment.id,
        word="μῆνιν",
        note="original note",
    )
    foreign = Annotation(
        user_id=other.id,
        lang_version_id=version.id,
        segment_id=segment.id,
        word="μῆνιν",
        note="other user's note",
    )
    session.add_all([owned, foreign])
    session.commit()

    app = FastAPI()
    app.include_router(router)  # router already declares prefix="/api/annotations"
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: owner

    ids = {"owned": owned.id, "foreign": foreign.id}
    yield TestClient(app), session, ids
    session.close()


def test_update_endpoint_exists_and_persists(ctx):
    """PUT is a declared route and actually writes the new note."""
    client, session, ids = ctx

    resp = client.put(f"/api/annotations/{ids['owned']}", json={"note": "edited note"})

    assert resp.status_code == 200, f"PUT not routed: {resp.status_code}"
    assert resp.json()["note"] == "edited note"

    session.expire_all()
    assert session.get(Annotation, ids["owned"]).note == "edited note"


def test_update_returns_full_response_shape(ctx):
    """The response serialises every AnnotationResponse field.

    Exercises AnnotationResponse.model_validate on the update path, which is
    where a bad model_validate kwarg would surface as a 500.
    """
    client, _, ids = ctx

    resp = client.put(f"/api/annotations/{ids['owned']}", json={"note": "shape check"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "id",
        "user_id",
        "lang_version_id",
        "segment_id",
        "word",
        "note",
        "created_at",
        "updated_at",
    }
    assert body["id"] == ids["owned"]


def test_update_another_users_annotation_is_404(ctx):
    """A foreign annotation must 404, not 403, and must not be modified.

    Ownership is folded into the WHERE clause, so a row the caller does not own
    is indistinguishable from one that does not exist - no existence leak.
    """
    client, session, ids = ctx

    resp = client.put(f"/api/annotations/{ids['foreign']}", json={"note": "hijacked"})

    assert resp.status_code == 404
    session.expire_all()
    assert session.get(Annotation, ids["foreign"]).note == "other user's note"


def test_update_missing_annotation_is_404(ctx):
    """An id that was never created 404s."""
    client, _, _ = ctx

    resp = client.put("/api/annotations/999999", json={"note": "ghost"})

    assert resp.status_code == 404


def test_update_requires_note(ctx):
    """note is required; an empty body is a validation error."""
    client, _, ids = ctx

    resp = client.put(f"/api/annotations/{ids['owned']}", json={})

    assert resp.status_code == 422
