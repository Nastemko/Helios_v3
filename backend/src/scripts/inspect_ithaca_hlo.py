"""Check whether XLA eliminates the unused Ithaca output heads under jit.

Beam search consumes only mask_logits and unk_logits (util/eval.py:166), yet the
model also computes logits_nsp (read by nothing), logits_date and
logits_subregion. Under jax.jit, XLA's dead-code elimination should drop all
three for free -- this script verifies that rather than hand-editing the shared
Model class, whose date/region heads the attribute path genuinely needs.

Run inside the backend image:

    docker run --rm -v "$PWD/backend/src:/app/src:ro,Z" \
      -e PYTHONPATH=/app/src helios-backend:perf \
      uv run python /app/src/scripts/inspect_ithaca_hlo.py
"""

import logging

import numpy as np

from services.ithaca_service.ithaca_service import BUCKET_SEQLEN, get_ithaca_service

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    service = get_ithaca_service()
    if not service.initialize_model("greek"):
        raise SystemExit("Greek model failed to initialize.")

    model = service._models["greek"]
    dummy = np.zeros((8, BUCKET_SEQLEN), dtype=np.int32)
    dummy[:, :10] = 1

    lowered = model.forward.lower(model.params, text_char=dummy, text_char_onehot=None)
    hlo = lowered.compile().as_text()
    lines = hlo.splitlines()

    print(f"HLO instruction count: {len(lines)}")
    for head in ("nsp", "date", "subregion"):
        hits = sum(1 for line in lines if head in line.lower())
        verdict = "likely eliminated" if hits == 0 else "still present"
        print(f"  references to {head!r}: {hits} ({verdict})")


if __name__ == "__main__":
    main()
