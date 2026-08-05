"""Benchmark Ithaca restoration and capture predictions for regression checks.

The perf work on the Ithaca service must not change what the model predicts,
so this script records both wall time and the full prediction list. Later runs
are diffed against the baseline to prove outputs are unchanged.

Runs standalone (no database needed). Inside the backend image:

    docker run --rm \
      -v "$PWD/backend/src:/app/src:ro,Z" -v "$PWD/bench:/bench:Z" \
      -e PYTHONPATH=/app/src helios-backend:perf \
      uv run python /app/src/scripts/bench_ithaca.py --out /bench/baseline.json
"""

import argparse
import json
import logging
import time
from typing import Any

from services.ithaca_service.ithaca_service import IthacaService, get_ithaca_service

logger = logging.getLogger(__name__)

# Each fixture must be >= MIN_TEXT_LEN (25 chars) after accent stripping, or
# _prepare_text raises "Input text too short". The '#' fixture exercises the
# unknown-length expansion path in beam search (util/eval.py:211-263), which is
# the case most likely to break under shape bucketing.
FIXTURES: list[dict[str, str]] = [
    {
        "name": "single_gap",
        "text": "εδοξεν τηι βουληι και τωι δημωι ????????? αθηναιων",
    },
    {
        "name": "unknown_length_gap",
        "text": "εδοξεν τηι βουληι και τωι δημωι # αθηναιων",
    },
    {
        "name": "multi_gap",
        "text": "αγαθηι τυχηι δεδοχθαι τηι βουληι ??? και τωι ??? δημωι",
    },
]


def run_fixture(
    service: IthacaService, fixture: dict[str, str], beam_width: int
) -> dict[str, Any]:
    """Run one restoration, recording timing and full prediction output."""
    start = time.perf_counter()
    result = service.restore(fixture["text"], language="greek", beam_width=beam_width)
    elapsed = time.perf_counter() - start

    candidates = result.predictions if result else []
    record = {
        "name": fixture["name"],
        "text": fixture["text"],
        "wall_seconds": round(elapsed, 3),
        "top_prediction": candidates[0].text if candidates else "",
        "top_score": candidates[0].score if candidates else 0.0,
        "predictions": [c.text for c in candidates],
    }
    logger.info("%s: %.1fs, %d candidates", fixture["name"], elapsed, len(candidates))
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Ithaca restoration.")
    parser.add_argument("--out", required=True, help="Path for the JSON report.")
    parser.add_argument("--beam-width", type=int, default=100)
    parser.add_argument(
        "--only",
        default=None,
        help="Run a single fixture by name (faster iteration during dev).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    service = get_ithaca_service()
    if not service.initialize_model("greek"):
        raise SystemExit("Greek model failed to initialize; check asset paths.")

    selected = [f for f in FIXTURES if args.only is None or f["name"] == args.only]
    if not selected:
        raise SystemExit(f"No fixture named {args.only!r}.")

    fixtures = [run_fixture(service, f, args.beam_width) for f in selected]
    report = {
        "beam_width": args.beam_width,
        "fixtures": fixtures,
        "total_wall_seconds": round(sum(f["wall_seconds"] for f in fixtures), 3),
    }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    logger.info("Wrote %s (total %.1fs)", args.out, report["total_wall_seconds"])


if __name__ == "__main__":
    main()
