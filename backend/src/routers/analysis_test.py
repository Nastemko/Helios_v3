"""Integration tests for POST /api/analyze/word.

Covers the HTTP layer the branch changed: `word_occurrence`/`context`
passthrough to the morphology service and the 422 bounds on
`word` (100), `context` (5000) and `word_occurrence` (>= 0).
The morphology service itself is faked — CLTK models are not needed.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.analysis import router
from services.morphology import MorphologyService, get_morphology_service


class _FakeMorphology(MorphologyService):
    """Records analyze_word() kwargs; returns a minimal valid response."""

    def __init__(self):
        # Skip __init__ (downloads CLTK models)
        self.calls = []

    async def analyze_word(self, word, language, context=None, word_occurrence=0):
        self.calls.append(
            {
                "word": word,
                "language": language,
                "context": context,
                "word_occurrence": word_occurrence,
            }
        )
        return {
            "word": word,
            "language": language,
            "lemma": word,
            "pos": "Noun",
            "morphology": {},
            "definitions": [],
            "lexicon_url": "",
            "perseus_url": None,
        }


@pytest.fixture
def client():
    """App with the morphology service replaced by the recording fake."""
    fake = _FakeMorphology()
    app = FastAPI()
    app.include_router(router)  # router already declares prefix="/api/analyze"
    app.dependency_overrides[get_morphology_service] = lambda: fake

    return TestClient(app), fake


def test_word_occurrence_reaches_service(client):
    """The clicked occurrence survives the HTTP layer into the service call."""
    test_client, fake = client

    resp = test_client.post(
        "/api/analyze/word",
        json={
            "word": "καὶ",
            "language": "grc",
            "context": "καὶ λόγος καὶ",
            "word_occurrence": 1,
        },
    )

    assert resp.status_code == 200
    assert fake.calls[0]["word_occurrence"] == 1
    assert fake.calls[0]["context"] == "καὶ λόγος καὶ"
    assert fake.calls[0]["word"] == "καὶ"


def test_defaults_when_occurrence_and_context_omitted(client):
    """Old clients that send only word+language still work."""
    test_client, fake = client

    resp = test_client.post(
        "/api/analyze/word", json={"word": "ξίφος", "language": "grc"}
    )

    assert resp.status_code == 200
    assert fake.calls[0]["word_occurrence"] == 0
    assert fake.calls[0]["context"] is None


def test_word_over_100_chars_is_422(client):
    """An unbounded word would be fed whole to Stanza; reject it at the edge."""
    test_client, _ = client

    resp = test_client.post(
        "/api/analyze/word", json={"word": "a" * 101, "language": "grc"}
    )

    assert resp.status_code == 422


def test_context_over_5000_chars_is_422(client):
    test_client, _ = client

    resp = test_client.post(
        "/api/analyze/word",
        json={"word": "x", "language": "grc", "context": "a" * 5001},
    )

    assert resp.status_code == 422


def test_negative_occurrence_is_422(client):
    """A negative occurrence has no meaning; it must not reach the service."""
    test_client, fake = client

    resp = test_client.post(
        "/api/analyze/word",
        json={"word": "x", "language": "grc", "word_occurrence": -1},
    )

    assert resp.status_code == 422
    assert fake.calls == []
