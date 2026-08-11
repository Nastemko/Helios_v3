"""Split one forward-pass batch across threads inside a single process.

The forward pass does not saturate a node: measured on the deployed
coordinator it peaks at ~280% of 600% CPU at beam 35, so roughly half the
machine sits idle during the most expensive operation in the system. Running
several smaller forward passes concurrently fills that gap, because XLA
releases the GIL and the calls genuinely overlap.

Measured on a 35-row batch, 6-core coordinator:

    whole batch      64.28s      1.00x
    2 chunks         48.49s      1.33x
    5 chunks         35.75s      1.80x

Running the same chunks *sequentially* gives only 0.98-1.17x, which is the
control that shows the gain is parallelism rather than a smaller-batch
effect.

This is the same row-independence that licenses cross-machine sharding, so
the two compose: a node chunks its own slice while the cluster splits the
batch between nodes.
"""

import concurrent.futures
import logging
from typing import Callable

import numpy as np

from services.ithaca_service.cpu_detect import effective_cpu_count

logger = logging.getLogger(__name__)

# Below this many rows per chunk the thread overhead is not repaid. Mirrors
# the cross-machine MIN_ROWS_PER_NODE guard for the same reason: the beam's
# head and tail are small, and splitting them wastes more than it saves.
DEFAULT_MIN_ROWS_PER_CHUNK = 4

ForwardChunk = Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]]


def resolve_chunk_count(configured: int) -> int:
    """Chunk count to use: the configured value, or autodetect when unset.

    Autodetection is deliberately the *default* rather than the only option.
    The two deployed nodes differ in architecture and in effective core count
    (a 6-core x86 coordinator and an ARM worker capped at 3), and the measured
    optimum does not track core count identically on both -- so a fixed
    formula cannot serve every machine and an override must always be
    available.
    """
    if configured > 0:
        return configured
    return effective_cpu_count()


def plan_chunks(
    batch_size: int, chunk_count: int, min_rows_per_chunk: int
) -> list[int]:
    """Return per-chunk row counts, or ``[batch_size]`` to run it whole.

    Rows are spread as evenly as possible with the remainder going to the
    earliest chunks, so 35 rows over 4 chunks is ``[9, 9, 9, 8]``. Mirrors
    ``distributed_forward.plan_split`` so both layers divide work the same way.
    """
    if chunk_count <= 1 or batch_size < min_rows_per_chunk * chunk_count:
        return [batch_size]

    base, remainder = divmod(batch_size, chunk_count)
    return [base + (1 if i < remainder else 0) for i in range(chunk_count)]


def chunked_forward(
    run: ForwardChunk,
    text_char: np.ndarray,
    chunk_count: int,
    min_rows_per_chunk: int = DEFAULT_MIN_ROWS_PER_CHUNK,
) -> tuple[np.ndarray, np.ndarray]:
    """Run ``run`` over row chunks concurrently and reassemble in order.

    ``run`` takes a row block and returns ``(mask_logits, unk_logits)``.

    Exceptions are deliberately *not* caught. The callers that need a
    degradation path (``DistributedForward``) already wrap this in one, and
    swallowing an error here would return a silently truncated batch --
    the one failure mode this subsystem must never have.
    """
    sizes = plan_chunks(text_char.shape[0], chunk_count, min_rows_per_chunk)
    if len(sizes) == 1:
        return run(text_char)

    bounds = []
    start = 0
    for size in sizes:
        bounds.append((start, start + size))
        start += size

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sizes)) as pool:
        # `map` preserves input order regardless of completion order, which is
        # what keeps rows aligned with the caller's beam_batch indexing.
        results = list(pool.map(lambda b: run(text_char[b[0] : b[1]]), bounds))

    logger.debug(
        "Chunked batch of %d into %s across threads", text_char.shape[0], sizes
    )

    mask_logits = np.concatenate([r[0] for r in results], axis=0)
    unk_logits = np.concatenate([r[1] for r in results], axis=0)
    return mask_logits, unk_logits
