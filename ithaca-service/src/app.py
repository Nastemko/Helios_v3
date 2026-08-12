"""HTTP surface for on-demand Ithaca/Aeneas inference.

This service exists so the production backend does not have to carry JAX. It
holds the checkpoints and exposes the three operations a user actually asks
for -- restore, attribute, contextualize -- one round trip each.

Deliberately *not* a forward-pass endpoint. The previous shard worker exposed
``/forward`` and was called once per beam-search generation (~35 times per
restoration); that is fine over a LAN but pathological over a network where
each hop costs a TLS handshake. Beam search stays inside this process.

Run locally with:

    PYTHONPATH=./src uv run uvicorn app:app --host 0.0.0.0 --port 8080
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from auth import validate_auth_config, verify_caller
from ithaca_service.ithaca_service import (
    DEFAULT_BEAM_WIDTH,
    DEFAULT_MAX_RESTORATION_LEN,
    MAX_BEAM_WIDTH,
    MAX_RESTORATION_LEN,
    Language,
    get_ithaca_service,
    initialize_all_models,
)

logger = logging.getLogger(__name__)

# Contextualization returns this many neighbours at most. Unbounded in the
# in-process version, where an oversized result was merely a big list; across
# the wire it is a response-size and serialisation cost, so it gets a ceiling.
MAX_TOP_K = 100


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load both checkpoints before serving.

    Done at startup rather than on first request so the readiness probe fails
    closed: an instance that cannot load its models never receives traffic,
    instead of accepting a request and taking a multi-second pickle load inside
    it. On a scale-to-zero platform this is also the cold-start cost, so it is
    the number to watch.

    Auth configuration is validated first, and deliberately raises: a service
    that cannot verify its callers should refuse to start rather than 500 on
    every inference request.
    """
    validate_auth_config()
    initialize_all_models()
    yield


app = FastAPI(
    title="Helios Ithaca Service",
    description="On-demand Ithaca (Greek) and Aeneas (Latin) inference.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Wire models
#
# The service layer returns plain dataclasses (ithaca_service/models.py). These
# Pydantic mirrors exist so FastAPI can validate and serialise them. They are
# intentionally field-for-field identical to what the backend's routers already
# emit, so moving the computation across a network changes no response body.
# ---------------------------------------------------------------------------


class RestorationCandidate(BaseModel):
    text: str
    restored_indices: list[int]
    score: float


class RestoreRequest(BaseModel):
    text: str
    language: Language = "greek"
    temperature: float = 1.0
    beam_width: int = Field(DEFAULT_BEAM_WIDTH, ge=1, le=MAX_BEAM_WIDTH)
    max_restoration_len: int = Field(
        DEFAULT_MAX_RESTORATION_LEN, ge=1, le=MAX_RESTORATION_LEN
    )


class RestoreResponse(BaseModel):
    input_text: str
    top_prediction: str
    missing_indices: list[int]
    predictions: list[RestorationCandidate]
    prediction_saliency: list[dict]
    available: bool
    message: Optional[str] = None


class LocationPrediction(BaseModel):
    location_id: int
    name: str
    score: float


class AttributeRequest(BaseModel):
    text: str
    language: Language = "greek"


class AttributeResponse(BaseModel):
    input_text: str
    locations: list[LocationPrediction]
    year_scores: list[float]
    # Computed from year_scores by a @property on the dataclass, which
    # `dataclasses.asdict` does not see. Serialised explicitly below -- dropping
    # it would silently blank the date range in the workbench UI.
    predicted_date_range: dict
    date_saliency: list[float]
    location_saliency: list[float]
    available: bool
    message: Optional[str] = None


class ContextualizeRequest(BaseModel):
    text: str
    language: Language = "greek"
    top_k: int = Field(20, ge=1, le=MAX_TOP_K)


class SimilarText(BaseModel):
    id: str
    ids_alt: Optional[dict] = None
    text: str
    location_id: Optional[int] = None
    date_min: Optional[int] = None
    date_max: Optional[int] = None
    score: float
    partner_link: Optional[str] = None


class ContextualizeResponse(BaseModel):
    similar: list[SimilarText]
    available: bool
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
#
# Each is `async def` with the blocking JAX call pushed to the threadpool.
# Running inference inline would stall the event loop and block this instance's
# own health check, which on Cloud Run reads as an unhealthy container.
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    """Readiness and per-language availability.

    Unauthenticated: Cloud Run's startup and liveness probes call this, and
    they do not present an ID token.
    """
    service = get_ithaca_service()
    status = service.get_status()
    return {
        "status": "ok",
        "models": status,
        "features": ["restore", "attribute", "contextualize"],
        "supported_languages": ["greek", "latin"],
    }


def _require_model(language: Language) -> None:
    """503 when the requested language did not load.

    A 503 (rather than the in-process stub response) lets the caller tell
    'this instance is broken' apart from 'the model declined your input'. The
    backend client turns it back into the familiar ``available=False`` body.
    """
    if not get_ithaca_service().is_available(language):
        raise HTTPException(
            status_code=503,
            detail=f"{language} model not loaded on this instance",
        )


@app.post("/restore", response_model=RestoreResponse)
async def restore(
    request: RestoreRequest, _: None = Depends(verify_caller)
) -> RestoreResponse:
    """Restore missing characters marked with '?' (one each) or '#' (unknown)."""
    _require_model(request.language)
    service = get_ithaca_service()

    result = await run_in_threadpool(
        service.restore,
        text=request.text,
        language=request.language,
        beam_width=request.beam_width,
        temperature=request.temperature,
        max_restoration_len=request.max_restoration_len,
    )

    return RestoreResponse(
        input_text=result.input_text,
        top_prediction=result.top_prediction,
        missing_indices=result.missing_indices,
        predictions=[
            RestorationCandidate(
                text=p.text, restored_indices=p.restored_indices, score=p.score
            )
            for p in result.predictions
        ],
        prediction_saliency=result.prediction_saliency,
        available=result.available,
        message=result.message,
    )


@app.post("/attribute", response_model=AttributeResponse)
async def attribute(
    request: AttributeRequest, _: None = Depends(verify_caller)
) -> AttributeResponse:
    """Predict date and geographic origin."""
    _require_model(request.language)
    service = get_ithaca_service()

    result = await run_in_threadpool(
        service.attribute, request.text, language=request.language
    )

    return AttributeResponse(
        input_text=result.input_text,
        locations=[
            LocationPrediction(
                location_id=loc.location_id, name=loc.name, score=loc.score
            )
            for loc in result.locations
        ],
        year_scores=result.year_scores,
        predicted_date_range=result.predicted_date_range,
        date_saliency=result.date_saliency,
        location_saliency=result.location_saliency,
        available=result.available,
        message=result.message,
    )


@app.post("/contextualize", response_model=ContextualizeResponse)
async def contextualize(
    request: ContextualizeRequest, _: None = Depends(verify_caller)
) -> ContextualizeResponse:
    """Find similar inscriptions in the training corpus."""
    _require_model(request.language)
    service = get_ithaca_service()

    result = await run_in_threadpool(
        service.contextualize,
        request.text,
        language=request.language,
        top_k=request.top_k,
    )

    return ContextualizeResponse(
        similar=[
            SimilarText(
                id=str(s.id),
                ids_alt=s.ids_alt,
                text=s.text,
                location_id=s.location_id,
                date_min=s.date_min,
                date_max=s.date_max,
                score=s.score,
                partner_link=s.partner_link,
            )
            for s in result.similar
        ],
        available=result.available,
        message=result.message,
    )
