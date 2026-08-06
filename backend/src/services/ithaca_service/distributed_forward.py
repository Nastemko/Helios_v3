"""Split a beam-search forward pass across a cluster of shard workers.

``beam_search_batch`` calls ``forward`` once per generation with a
``(beam_width, seq_len)`` array of candidate rows. Every row is independent
through the model, so the batch can be split across machines and concatenated
back in order. Verified bit-exact:

    forward(rows 0..34) == concat(forward(0..17), forward(18..34))
    mask_logits: max abs diff = 0.0    unk_logits: max abs diff = 0.0

That matters because the returned logits feed a length-normalised prune; any
drift would silently change which candidates survive.

Why this rather than more cores: the forward pass is ~49% serial and saturates
around two cores, so tripling vCPUs buys ~11%. Each shard runs a *complete*
forward pass on its own slice, so the serial section runs in parallel too.

The wrapper degrades rather than fails -- any shard error or timeout falls back
to computing the whole batch locally.
"""

import concurrent.futures
import io
import logging
from typing import Any, Callable

import httpx
import numpy as np

logger = logging.getLogger(__name__)

# Row counts below this per node are cheaper to run locally than to ship: per-row
# cost is flat down to batch 4 and collapses below it, and a round trip is pure
# overhead on top. Callers override via settings.ithaca_shard.MIN_ROWS_PER_NODE.
DEFAULT_MIN_ROWS_PER_NODE = 4


def encode_batch(text_char: np.ndarray) -> bytes:
    """Serialise a token block for the wire.

    ``.npy`` rather than JSON: a float32 logit array is ~10x larger as JSON and
    costs more to parse than the transfer saves.
    """
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(text_char), allow_pickle=False)
    return buffer.getvalue()


def decode_batch(payload: bytes) -> np.ndarray:
    """Inverse of :func:`encode_batch`."""
    return np.load(io.BytesIO(payload), allow_pickle=False)


def encode_logits(mask_logits: np.ndarray, unk_logits: np.ndarray) -> bytes:
    """Pack both logit arrays a worker returns into one payload."""
    buffer = io.BytesIO()
    np.savez(
        buffer,
        mask_logits=np.asarray(mask_logits, dtype=np.float32),
        unk_logits=np.asarray(unk_logits, dtype=np.float32),
    )
    return buffer.getvalue()


def decode_logits(payload: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of :func:`encode_logits`."""
    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
        return data["mask_logits"], data["unk_logits"]


def plan_split(batch_size: int, node_count: int, min_rows_per_node: int) -> list[int]:
    """Return per-node row counts, or ``[batch_size]`` to stay local.

    Rows are spread as evenly as possible with the remainder going to the
    earliest nodes, so beam 35 over 3 nodes is ``[12, 12, 11]``. The
    coordinator's slice is index 0.
    """
    if node_count <= 1 or batch_size < min_rows_per_node * node_count:
        return [batch_size]

    base, remainder = divmod(batch_size, node_count)
    return [base + (1 if i < remainder else 0) for i in range(node_count)]


def _offsets(sizes: list[int]) -> list[tuple[int, int]]:
    """Turn row counts into (start, stop) slice bounds."""
    bounds = []
    start = 0
    for size in sizes:
        bounds.append((start, start + size))
        start += size
    return bounds


class DistributedForward:
    """Wraps a local ``forward`` so each call is split across the cluster.

    The signature matches what ``beam_search_batch`` invokes, so this drops in
    at the ``IthacaModel.forward`` seam with no change to vendored code.
    """

    def __init__(
        self,
        local_forward: Callable[..., Any],
        shard_urls: list[str],
        language: str,
        timeout: float = 60.0,
        min_rows_per_node: int = DEFAULT_MIN_ROWS_PER_NODE,
    ) -> None:
        self.local_forward = local_forward
        self.shard_urls = list(shard_urls)
        self.language = language
        self.timeout = timeout
        self.min_rows_per_node = min_rows_per_node
        # Coordinator plus each remote worker.
        self.node_count = len(self.shard_urls) + 1
        self._client = httpx.Client(timeout=timeout)

    def _call_local(
        self, params: Any, text_char: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run a slice through the in-process model.

        ``params`` is threaded through explicitly rather than stashed on the
        instance: Flax's ``apply`` requires it positionally, and an instance
        attribute would be shared mutable state across concurrent calls.
        """
        _, _, mask_logits, _, unk_logits = self.local_forward(
            params,
            text_char=text_char,
            text_char_onehot=None,
            vision_img=None,
            vision_available=None,
        )
        return np.asarray(mask_logits), np.asarray(unk_logits)

    def _call_remote(
        self, url: str, text_char: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run a slice on a worker."""
        response = self._client.post(
            f"{url.rstrip('/')}/forward",
            content=encode_batch(text_char),
            headers={"Content-Type": "application/octet-stream"},
            params={"language": self.language},
        )
        response.raise_for_status()
        return decode_logits(response.content)

    def __call__(
        self,
        params: Any,
        text_char: np.ndarray | None = None,
        text_char_onehot: Any = None,
        vision_img: Any = None,
        vision_available: Any = None,
        **kwargs: Any,
    ) -> tuple[Any, Any, np.ndarray, Any, np.ndarray]:
        """Compute one generation's logits, sharded when it pays to be.

        Returns the same 5-tuple shape as the vendored model's ``apply``; only
        the mask and unk logits are populated, which is all restore reads.
        """
        # Vision inputs are broadcast per batch element upstream, so a split
        # would need them sliced too. restore() never sends them; bail out
        # rather than silently mis-shard if that ever changes.
        if text_char is None or vision_img is not None or vision_available is not None:
            return self.local_forward(
                params,
                text_char=text_char,
                text_char_onehot=text_char_onehot,
                vision_img=vision_img,
                vision_available=vision_available,
            )

        sizes = plan_split(text_char.shape[0], self.node_count, self.min_rows_per_node)
        if len(sizes) == 1:
            mask_logits, unk_logits = self._call_local(params, text_char)
            return None, None, mask_logits, None, unk_logits

        bounds = _offsets(sizes)
        try:
            # The coordinator computes its own slice while the workers run, so
            # all three nodes are busy; waiting on remotes first would waste one.
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(self.shard_urls)
            ) as pool:
                futures = [
                    pool.submit(self._call_remote, url, text_char[start:stop])
                    for url, (start, stop) in zip(self.shard_urls, bounds[1:])
                ]
                local_start, local_stop = bounds[0]
                results = [self._call_local(params, text_char[local_start:local_stop])]
                # Order matters: beam_batch is indexed positionally against these
                # rows, so results must line up with the original batch order.
                results.extend(
                    future.result(timeout=self.timeout) for future in futures
                )
        except Exception as exc:
            # exc_info because the fallback is silent by design: without a
            # traceback a misconfigured cluster looks like plain slowness,
            # since every generation still returns the right answer locally.
            logger.warning(
                "Shard fan-out failed (%s); computing batch of %d locally",
                exc,
                text_char.shape[0],
                exc_info=True,
            )
            mask_logits, unk_logits = self._call_local(params, text_char)
            return None, None, mask_logits, None, unk_logits

        mask_logits = np.concatenate([r[0] for r in results], axis=0)
        unk_logits = np.concatenate([r[1] for r in results], axis=0)
        return None, None, mask_logits, None, unk_logits

    def close(self) -> None:
        """Release the pooled HTTP connections."""
        self._client.close()
