"""Forward-pass-only worker for distributed Ithaca inference.

Runs on each extra machine in the cluster. It holds the same checkpoints as the
coordinator and exposes exactly one operation: run a block of candidate rows
through the model and return the logits.

The beam search itself -- pruning, scoring, candidate expansion -- stays on the
coordinator. Only the forward pass is distributed, because that is where
essentially all the time goes (the pure-Python bookkeeping is ~44ms per
generation against ~10s of model compute).

Run with:

    PYTHONPATH=./src uv run uvicorn \
        services.ithaca_service.shard_worker:app --host 0.0.0.0 --port 8001
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from services.ithaca_service.distributed_forward import decode_batch, encode_logits
from services.ithaca_service.ithaca_service import (
    Language,
    get_ithaca_service,
    initialize_all_models,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load checkpoints up front so the first restore is not penalised."""
    initialize_all_models()
    yield


app = FastAPI(
    title="Ithaca Shard Worker",
    description="Forward-pass-only worker for distributed Ithaca inference.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, object]:
    """Report which languages this worker can serve."""
    service = get_ithaca_service()
    return {
        "status": "ok",
        "languages": {
            language: service.is_available(language) for language in ("greek", "latin")
        },
    }


def _run_forward(body: bytes, language: Language) -> bytes:
    """Decode a batch, run it through the model, encode the logits.

    Split out of the endpoint so the blocking JAX call can be handed to the
    threadpool rather than run on the event loop.
    """
    service = get_ithaca_service()
    model = service._models[language]
    try:
        text_char = decode_batch(body)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Could not decode batch: {exc}"
        ) from exc

    _, _, mask_logits, _, unk_logits = model.forward(
        model.params,
        text_char=text_char,
        text_char_onehot=None,
        vision_img=None,
        vision_available=None,
    )
    return encode_logits(mask_logits, unk_logits)


# `async def` so the body can be awaited, with the blocking forward pass pushed
# to the threadpool -- running JAX inline would stall the event loop and block
# this worker's own /health.
@app.post("/forward")
async def forward(request: Request, language: Language = "greek") -> Response:
    """Run one block of candidate rows through the model.

    Body is a ``.npy``-encoded ``(rows, seq_len)`` int array; the response packs
    ``mask_logits`` and ``unk_logits`` into a single ``.npz``.
    """
    service = get_ithaca_service()
    if not service.is_available(language):
        raise HTTPException(
            status_code=503, detail=f"{language} model not loaded on this worker"
        )

    body = await request.body()
    payload = await run_in_threadpool(_run_forward, body, language)
    return Response(content=payload, media_type="application/octet-stream")
