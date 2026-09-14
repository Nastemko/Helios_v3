"""Tests for the inscriptions API response contract.

Inscription.metadata_raw is a JSONB column, so SQLAlchemy hands the router a
dict. TextResponse previously declared it as a string, which Pydantic v2 will
not coerce — every detail request 500'd once the loader started populating the
column with residual PHI fields.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from middleware.auth import get_current_user
from routers.inscriptions import (
    AttributeRequest,
    ContextualizeRequest,
    RestoreRequest,
    TextResponse,
    router,
)
from services.ithaca.schemas import RestorationResult
from services.ithaca.service import BusyError

# Long enough to clear the model's 25-character minimum.
GREEK_WITH_GAPS = "εδοξεν τηι βουληι και τωι δημωι ????? αθηναιων"

# The three model endpoints must agree on notation; parametrizing over them is
# what catches a validator that was only ever wired to one of them.
TEXT_REQUEST_MODELS = [RestoreRequest, AttributeRequest, ContextualizeRequest]


def _residual_metadata() -> dict:
    """Residual PHI metadata shaped like the real iphi.json leftovers."""
    return {
        "ids_alt": {"phi_id": 232883},
        "region_main_id": "1701",
        "partner_link": "https://example.org/phi/232883",
    }


def test_text_response_accepts_dict_metadata():
    """metadata_raw is a JSONB column, so the response model must accept a dict."""
    response = TextResponse(
        id=1,
        title="Dedication to Athena",
        text="μῆνιν ἄειδε θεά",
        metadata_raw=_residual_metadata(),
    )

    assert response.metadata_raw == _residual_metadata()


def test_text_response_preserves_nested_metadata():
    """Nested PHI structures survive serialization rather than being stringified."""
    response = TextResponse(
        id=1,
        title="Dedication to Athena",
        text="μῆνιν ἄειδε θεά",
        metadata_raw=_residual_metadata(),
    )

    dumped = response.model_dump()

    assert dumped["metadata_raw"]["ids_alt"] == {"phi_id": 232883}


def test_text_response_allows_null_metadata():
    """An inscription whose residual metadata is empty serializes as null."""
    response = TextResponse(
        id=1,
        title="Dedication to Athena",
        text="μῆνιν ἄειδε θεά",
        metadata_raw=None,
    )

    assert response.metadata_raw is None


def test_text_response_rejects_non_object_metadata():
    """A bare string is not valid residual metadata and must not be accepted."""
    with pytest.raises(ValidationError):
        TextResponse(
            id=1,
            title="Dedication to Athena",
            text="μῆνιν ἄειδε θεά",
            metadata_raw="not-an-object",
        )


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS)
def test_hyphen_is_rejected_on_every_model_endpoint(model):
    """'-' must be refused everywhere, not just on /restore.

    The rewrite used to live on RestoreRequest alone, so a '-' sent to
    /attribute or /contextualize reached the tokenizer as the model's internal
    `missing` token: never added to restore_mask_idx, so never filled, and
    reported as a success.
    """
    with pytest.raises(ValidationError) as exc_info:
        model(text=GREEK_WITH_GAPS.replace("?", "-"))

    message = str(exc_info.value)
    assert "'?'" in message and "'#'" in message


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS)
def test_gap_notation_passes_through_unmodified(model):
    """'?' and '#' are the model's own notation and must not be rewritten."""
    text = "εδοξεν τηι βουληι και τωι δημωι ????? # αθηναιων"

    assert model(text=text).text == text


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS)
def test_text_without_gaps_is_accepted(model):
    """Attribution and contextualization run on complete texts too."""
    text = "ευψυχι αλεξανδρε ουδεις αθανατος"

    assert model(text=text).text == text


@pytest.mark.parametrize("bad_length", [0, 21])
def test_max_restoration_len_is_bounded(bad_length):
    """Out-of-range values raise inside the model code, which the service
    swallows into an empty result — so reject them at the boundary instead."""
    with pytest.raises(ValidationError):
        RestoreRequest(text=GREEK_WITH_GAPS, max_restoration_len=bad_length)


@pytest.mark.parametrize("good_length", [1, 15, 20])
def test_max_restoration_len_accepts_the_supported_range(good_length):
    """UNK_RESTORATION_MAX_LEN is 20, so 1..20 must all be valid."""
    request = RestoreRequest(text=GREEK_WITH_GAPS, max_restoration_len=good_length)

    assert request.max_restoration_len == good_length


# --- Router-level tests for the async model endpoints ---
#
# The endpoints call get_ithaca_service() inline (not via Depends), so the
# singleton is patched in the routers.inscriptions namespace. Auth is
# overridden — these tests pin routing/error-mapping, not ownership.


def _mock_service(**methods):
    """An IthacaService stand-in with an available model and stubbed methods."""
    service = MagicMock()
    service.is_available.return_value = True
    for name, fn in methods.items():
        setattr(service, name, fn)
    return service


@pytest.fixture
def model_client(monkeypatch):
    """TestClient with auth stubbed; service installed per-test via `use`."""

    def use(service):
        monkeypatch.setattr("routers.inscriptions.get_ithaca_service", lambda: service)

    app = FastAPI()
    app.include_router(router)  # router already declares prefix="/api/inscriptions"
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=1)

    return TestClient(app), use


def test_restore_success_response_shape(model_client):
    """A good result passes through with available=True and the prediction."""
    client, use = model_client

    async def succeed(**kwargs):
        return RestorationResult(
            input_text=GREEK_WITH_GAPS,
            top_prediction="εδοξεν τηι βουληι FULL αθηναιων",
            missing_indices=[32, 33, 34, 35, 36],
            predictions=[],
            prediction_saliency=[],
            available=True,
            message=None,
        )

    use(_mock_service(restore=succeed))

    resp = client.post(
        "/api/inscriptions/restore",
        json={"text": GREEK_WITH_GAPS, "language": "greek"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["top_prediction"] == "εδοξεν τηι βουληι FULL αθηναιων"
    assert body["missing_indices"] == [32, 33, 34, 35, 36]


def test_restore_unavailable_model_short_circuits(model_client):
    """No model → available=False with a status hint; inference never runs."""
    client, use = model_client

    async def must_not_run(**kwargs):
        raise AssertionError("inference must not be called without a model")

    service = _mock_service(restore=must_not_run)
    service.is_available.return_value = False
    use(service)

    resp = client.post(
        "/api/inscriptions/restore",
        json={"text": GREEK_WITH_GAPS, "language": "greek"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert "not loaded" in (body["message"] or "")


@pytest.mark.parametrize(
    "endpoint,method",
    [
        ("restore", "restore"),
        ("attribute", "attribute"),
        ("contextualize", "contextualize"),
    ],
)
def test_busy_model_maps_to_429_on_every_endpoint(model_client, endpoint, method):
    """A second concurrent inference fails fast instead of queueing.

    The service raises BusyError; every model endpoint must map it to 429.
    """
    client, use = model_client

    async def busy(*args, **kwargs):
        raise BusyError("An inference is already running; try again later.")

    use(_mock_service(**{method: busy}))

    resp = client.post(
        f"/api/inscriptions/{endpoint}",
        json={"text": GREEK_WITH_GAPS, "language": "greek"},
    )

    assert resp.status_code == 429
    assert "already running" in resp.json()["detail"]
