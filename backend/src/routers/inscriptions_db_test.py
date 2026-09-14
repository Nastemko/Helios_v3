"""Integration tests for the inscriptions DB-read endpoints.

Covers the `async def` → `def` conversion of the browsing routes: list,
detail, regions and stats run against a seeded in-memory SQLite DB.

`Inscription.metadata_raw` is a JSONB column, which SQLite cannot render at
DDL time, so table creation temporarily swaps the column type to generic JSON
(the columns are restored before any query runs).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models.inscription import Inscription, InscriptionSegment
from routers.inscriptions import router


@pytest.fixture
def client():
    """App wired to an in-memory SQLite DB with two seeded inscriptions."""
    # StaticPool + check_same_thread=False: TestClient serves requests on a
    # separate thread, and a default SQLite connection is bound to its creator.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata_col = Inscription.__table__.c.metadata_raw
    original_type = metadata_col.type
    metadata_col.type = JSON()
    try:
        Base.metadata.create_all(
            engine,
            tables=[Inscription.__table__, InscriptionSegment.__table__],
        )
    finally:
        metadata_col.type = original_type
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    dedication = Inscription(
        phi_id=1001,
        title="Dedication to Athena",
        region_main="Attica",
        region_sub="Athens",
        date_min=-460,
        date_max=-440,
        date_str="c. 450 BC",
        date_circa=True,
        metadata_raw={"ids_alt": {"phi_id": 1001}},
    )
    epitaph = Inscription(
        phi_id=1002,
        title="Epitaph",
        region_main="Boeotia",
        metadata_raw=None,
    )
    session.add_all([dedication, epitaph])
    session.flush()

    session.add_all(
        [
            InscriptionSegment(
                inscription_id=dedication.id, sequence=1, content="μῆνιν ἄειδε"
            ),
            InscriptionSegment(
                inscription_id=dedication.id, sequence=2, content="θεὰ Πηληϊάδεω"
            ),
            InscriptionSegment(
                inscription_id=epitaph.id, sequence=1, content="ευψυχι αλεξανδρε"
            ),
        ]
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)  # router already declares prefix="/api/inscriptions"
    app.dependency_overrides[get_db] = lambda: session

    yield TestClient(app)
    session.close()


def test_list_returns_seeded_rows_with_preview(client):
    """Both inscriptions are listed with the first segment as preview."""
    resp = client.get("/api/inscriptions/")

    assert resp.status_code == 200
    titles = [row["title"] for row in resp.json()]
    assert titles == ["Dedication to Athena", "Epitaph"]
    assert resp.json()[0]["text_preview"] == "μῆνιν ἄειδε"


def test_list_search_filters_by_segment_content(client):
    """search matches segment text, not just the inscription row."""
    resp = client.get("/api/inscriptions/", params={"search": "ἄειδε"})

    assert resp.status_code == 200
    assert [row["title"] for row in resp.json()] == ["Dedication to Athena"]


def test_list_region_filter(client):
    resp = client.get("/api/inscriptions/", params={"region_main": "Boeotia"})

    assert resp.status_code == 200
    assert [row["title"] for row in resp.json()] == ["Epitaph"]


def test_detail_joins_segments_and_returns_dict_metadata(client):
    """Full text is the segments joined in order; metadata_raw stays a dict."""
    dedication_id = client.get("/api/inscriptions/").json()[0]["id"]

    resp = client.get(f"/api/inscriptions/{dedication_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "μῆνιν ἄειδε. θεὰ Πηληϊάδεω"
    assert body["metadata_raw"] == {"ids_alt": {"phi_id": 1001}}
    assert body["date_min"] == -460


def test_detail_unknown_id_is_404(client):
    resp = client.get("/api/inscriptions/999999")

    assert resp.status_code == 404


def test_stats_count_seeded_corpus(client):
    """Only one of the two inscriptions carries dates; two regions exist."""
    resp = client.get("/api/inscriptions/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_inscriptions"] == 2
    assert body["inscriptions_with_dates"] == 1
    assert body["regions_count"] == 2
    assert body["date_range"] == {"earliest": -460, "latest": -440}


def test_regions_lists_both_mains_with_counts(client):
    resp = client.get("/api/inscriptions/regions")

    assert resp.status_code == 200
    counts = {row["region"]: row["count"] for row in resp.json()}
    assert counts == {"Attica": 1, "Boeotia": 1}
