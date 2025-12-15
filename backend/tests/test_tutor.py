from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from models.text import Text, TextSegment
from routers.tutor import router
from services.llm import LLMProvider
from services.tutor import (
    TranslationSuggestion,
    TutorService,
    get_tutor_service,
)
from database import get_db


class DummyLLMProvider(LLMProvider):
    async def suggest_translation(
        self, prompt: str, *, system_prompt: str | None = None
    ) -> str:
        return (
            '{'
            '"translation": "LLM generated translation.",'
            '"literal_gloss": "Literal gloss content.",'
            '"rationale": "Explains why this translation makes sense.",'
            '"confidence": 0.9'
            '}'
        )


class BrokenLLMProvider(LLMProvider):
    async def suggest_translation(
        self, prompt: str, *, system_prompt: str | None = None
    ) -> str:
        return "This is not JSON"


@pytest.fixture
def sample_text() -> Text:
    return Text(
        id=1,
        urn="urn:cts:sample",
        author="Homer",
        title="Iliad",
        language="grc",
        is_fragment=False,
        text_metadata={},
    )


@pytest.fixture
def sample_segment(sample_text: Text) -> TextSegment:
    return TextSegment(
        id=10,
        text_id=sample_text.id,
        book="1",
        line="1",
        sequence=1,
        content="μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        reference="1.1",
    )


@pytest.mark.asyncio
async def test_tutor_service_returns_structured_response(sample_text, sample_segment):
    service = TutorService(llm_provider=DummyLLMProvider())
    suggestion = await service.suggest_translation(
        text=sample_text,
        segment=sample_segment,
        selection="μῆνιν ἄειδε",
        translation_draft=None,
        language="grc",
        metadata={"student_level": "beginner"},
    )

    assert suggestion.translation == "LLM generated translation."
    assert suggestion.literal_gloss == "Literal gloss content."
    assert suggestion.source_language == "grc"
    assert suggestion.segment_reference == "1.1"
    assert suggestion.metadata["student_level"] == "beginner"


@pytest.mark.asyncio
async def test_tutor_service_handles_unparseable_response(
    sample_text, sample_segment
):
    service = TutorService(llm_provider=BrokenLLMProvider())
    suggestion = await service.suggest_translation(
        text=sample_text,
        segment=sample_segment,
        selection="μῆνιν ἄειδε",
        translation_draft=None,
        language="grc",
        metadata={},
    )

    assert suggestion.translation == "This is not JSON"
    assert "raw_response" in suggestion.metadata


class FakeQuery:
    def __init__(self, segment: TextSegment):
        self._segment = segment

    def filter(self, *args: Any, **kwargs: Any) -> "FakeQuery":
        return self

    def first(self) -> TextSegment:
        return self._segment


class FakeSession:
    def __init__(self, text: Text, segment: TextSegment):
        self._text = text
        self._segment = segment

    def get(self, model, pk: int):
        if model is Text and pk == self._text.id:
            return self._text
        return None

    def query(self, model):
        if model is TextSegment:
            return FakeQuery(self._segment)
        raise AssertionError("Unexpected model queried")

    def close(self):
        pass


class DummyTutorService(TutorService):
    def __init__(self, suggestion: TranslationSuggestion):
        self._suggestion = suggestion

    async def suggest_translation(self, **kwargs: Dict[str, Any]) -> TranslationSuggestion:  # type: ignore[override]
        return self._suggestion


@pytest.fixture
def tutor_app(sample_text, sample_segment):
    app = FastAPI()
    fake_db = FakeSession(sample_text, sample_segment)
    suggestion = TranslationSuggestion(
        translation="Router level translation",
        literal_gloss=None,
        rationale="Provided by dummy service.",
        confidence=0.8,
        source_language="grc",
        segment_reference="1.1",
        context_excerpt="μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        metadata={},
    )
    dummy_service = DummyTutorService(suggestion)

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tutor_service] = lambda: dummy_service
    app.include_router(router)
    return app


def test_tutor_router_returns_success_when_enabled(monkeypatch, tutor_app):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    client = TestClient(tutor_app)

    response = client.post(
        "/api/tutor/suggest-translation",
        json={
            "text_id": 1,
            "segment_id": 10,
            "selection": "μῆνιν ἄειδε",
            "language": "grc",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["translation"] == "Router level translation"
    assert data["rationale"] == "Provided by dummy service."


def test_tutor_router_blocks_when_llm_disabled(monkeypatch, tutor_app):
    monkeypatch.setattr(settings, "LLM_ENABLED", False)
    client = TestClient(tutor_app)

    response = client.post(
        "/api/tutor/suggest-translation",
        json={
            "text_id": 1,
            "segment_id": 10,
            "selection": "μῆνιν ἄειδε",
            "language": "grc",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "LLM features are currently disabled"


