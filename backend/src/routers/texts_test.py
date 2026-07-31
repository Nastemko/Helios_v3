"""Tests for the /api/texts list filters.

Covers the interaction between `search` (which matches across all languages,
including translations) and `author`/`language`, which previously either
dropped legitimate hits or silently ignored a bad value.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models.text import Language, LiteraryText, LiteraryTextLangVersion
from routers.texts import router


@pytest.fixture
def client():
    """App wired to an in-memory SQLite DB seeded with one work in two languages."""
    # StaticPool + check_same_thread=False: TestClient serves requests on a
    # separate thread, and a default SQLite connection is bound to its creator.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[LiteraryText.__table__, LiteraryTextLangVersion.__table__],
    )
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    work = LiteraryText(local_id="tlg0012.tlg001")
    session.add(work)
    session.flush()

    # The Greek original carries a transliterated author; the English
    # translation carries the anglicised one. A search for "Homer" matches only
    # the translation, but the endpoint returns the Greek row.
    session.add_all(
        [
            LiteraryTextLangVersion(
                local_id="tlg0012.tlg001.perseus-grc1",
                literary_text_id=work.id,
                language=Language.GRC,
                author="Ὅμηρος",
                title="Ἰλιάς",
            ),
            LiteraryTextLangVersion(
                local_id="tlg0012.tlg001.perseus-eng1",
                literary_text_id=work.id,
                language=Language.EN,
                author="Homer",
                title="The Iliad",
                translator="Samuel Butler",
            ),
        ]
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)  # router already declares prefix="/api/texts"
    app.dependency_overrides[get_db] = lambda: session

    yield TestClient(app)
    session.close()


def test_search_alone_finds_work_via_translation(client):
    """Baseline: searching an anglicised author returns the Greek original."""
    resp = client.get("/api/texts/", params={"search": "Homer"})

    assert resp.status_code == 200
    assert [t["language"] for t in resp.json()] == ["grc"]


def test_search_combined_with_author_still_matches(client):
    """search + author must not cancel each other out.

    Both filters match the English translation, but the returned row is the
    Greek version whose author is 'Ὅμηρος'. Filtering the returned row drops
    the hit entirely.
    """
    resp = client.get("/api/texts/", params={"search": "Homer", "author": "Homer"})

    assert resp.status_code == 200
    assert len(resp.json()) == 1, "search+author returned nothing; filters collided"


def test_invalid_language_is_rejected(client):
    """A language that is not a valid enum member must 422, not return everything."""
    resp = client.get("/api/texts/", params={"language": "english"})

    assert resp.status_code == 422


def test_disallowed_language_is_rejected(client):
    """A valid enum member outside ALLOWED_LANGUAGES must 422 too."""
    resp = client.get("/api/texts/", params={"language": "en"})

    assert resp.status_code == 422


def test_allowed_language_filters(client):
    """A supported language still filters normally."""
    resp = client.get("/api/texts/", params={"language": "grc"})

    assert resp.status_code == 200
    assert [t["language"] for t in resp.json()] == ["grc"]
