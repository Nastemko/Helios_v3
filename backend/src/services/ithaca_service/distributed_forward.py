"""Split a beam-search forward pass across a cluster of shard workers.

``beam_search_batch`` calls ``forward`` once per generation with a
``(beam_width, seq_len)`` array of candidate rows. Every row is independent
through the model, so the batch can be split across machines and concatenated
back in order. Verified bit-exact:

    forward(rows 0..34) == concat(forward(0..17), forward(18..34))
    mask_logits: max abs diff = 0.0    unk_logits: max abs diff = 0.0

That matters because the returned logits feed a length-normalised prune; any
drift would silently change which candidates survive.

Why shard at all, given each node also chunks its slice internally (see
chunked_forward.py): the two are complementary. Chunking fills one machine's
idle cores -- measured 1.80x -- while sharding adds machines. Neither subsumes
the other, and chunking is the larger lever of the two: a 2-node cluster
measured 16-29% end to end.

The wrapper degrades rather than fails -- any shard error or timeout falls back
to computing the whole batch locally.
"""

import concurrent.futures
import io
import logging
from typing import Any, Callable

import httpx
import numpy as np

from services.ithaca_service.chunked_forward import chunked_forward

logger = logging.getLogger(__name__)

# Row counts below this per node are cheaper to run locally than to ship: a
# round trip is pure overhead that a small slice cannot repay. Callers override
# via settings.ithaca_shard.MIN_ROWS_PER_NODE. Pending a re-measure -- see the
# note on that setting in config.py.
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


# Keyword arguments that only non-restore call sites use. Their presence means
# this is an embedding, saliency or attribution call, whose shape the shard
# protocol cannot reproduce -- shard_worker only speaks "token block in,
# mask+unk logits out".
#
# Matched on key presence, not value: saliency_loss_mask (eval.py:534) passes an
# explicit `text_char_onehot=None`, so a value test would misread it. Listed by
# name rather than inferred because the cost of guessing wrong is asymmetric --
# wrongly sharding corrupts a beam prune silently, wrongly declining just runs
# locally.
_NON_RESTORE_KWARGS = frozenset({"text_char_emb", "padding", "output_return_emb"})


def _vision_in_use(vision_available: Any) -> bool:
    """Whether ``vision_available`` marks any row as actually carrying an image.

    Deliberately not a ``is not None`` test. ``beam_search_batch`` defaults the
    parameter to ``False`` rather than ``None`` and repeats it across the batch,
    so the restore path always supplies a non-None array of falses -- which
    means nothing is available. Only a truthy entry indicates real vision input.
    """
    if vision_available is None:
        return False
    return bool(np.any(np.asarray(vision_available)))


def _offsets(sizes: list[int]) -> list[tuple[int, int]]:
    """Turn row counts into (start, stop) slice bounds."""
    bounds = []
    start = 0
    for size in sizes:
        bounds.append((start, start + size))
        start += size
    return bounds


class DistributedForward:
    """A transparent proxy for ``forward`` that shards the restore beam batch.

    Drops in at the ``IthacaModel.forward`` seam with no change to vendored
    code. Calls that match the restore batch shape are split across the
    cluster; every other shape -- embeddings, saliency gradients, attribution
    -- is forwarded to the local model untouched and its result returned
    verbatim, because the worker protocol cannot serve them and their return
    arity is not even fixed. See ``__call__`` and ``_is_shardable``.
    """

    def __init__(
        self,
        local_forward: Callable[..., Any],
        shard_urls: list[str],
        language: str,
        timeout: float = 60.0,
        min_rows_per_node: int = DEFAULT_MIN_ROWS_PER_NODE,
        local_chunks: int = 0,
        min_rows_per_chunk: int = 4,
    ) -> None:
        self.local_forward = local_forward
        self.shard_urls = list(shard_urls)
        self.language = language
        self.timeout = timeout
        self.min_rows_per_node = min_rows_per_node
        # 0 or 1 disables chunking, keeping the single-call path exactly as
        # before. The caller resolves autodetection, so this stays a plain int.
        self.local_chunks = local_chunks
        self.min_rows_per_chunk = min_rows_per_chunk
        # Coordinator plus each remote worker.
        self.node_count = len(self.shard_urls) + 1
        self._client = httpx.Client(timeout=timeout)

    def _call_local(
        self, params: Any, text_char: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run one restore-shaped slice through the in-process model.

        Unlike ``__call__`` this is not a general proxy and does not need to
        be: both callers (the coordinator's own slice, and the whole-batch
        error fallback) run only after ``_is_shardable`` has established the
        exact call shape. It also has a different return contract --
        ``(mask, unk)`` as numpy, matching ``_call_remote`` so the two can be
        concatenated together.

        Hardcoding the vision kwargs to None is therefore safe rather than
        arbitrary: ``_is_shardable`` has already ruled out any vision data,
        and an all-False ``vision_available`` with no ``vision_img`` is inert
        in the model (models/model.py only consults it inside the
        ``vision_img is not None`` branch). The sharded-vs-local equality
        tests pin that this stays bit-identical.

        ``params`` is threaded through explicitly rather than stashed on the
        instance: Flax's ``apply`` requires it positionally, and an instance
        attribute would be shared mutable state across concurrent calls. That
        matters more now that the slice below is computed on several threads
        at once.

        The slice is split across threads when ``local_chunks`` allows it.
        The forward pass leaves about half of each node's CPU idle, and rows
        are independent through the model, so overlapping several smaller
        passes is bit-exact and recovers that headroom.
        """

        def run(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            _, _, mask_logits, _, unk_logits = self.local_forward(
                params,
                text_char=rows,
                text_char_onehot=None,
                vision_img=None,
                vision_available=None,
            )
            return np.asarray(mask_logits), np.asarray(unk_logits)

        return chunked_forward(
            run,
            text_char,
            chunk_count=self.local_chunks,
            min_rows_per_chunk=self.min_rows_per_chunk,
        )

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

    def _is_shardable(self, args: tuple, kwargs: dict) -> bool:
        """Whether this call has the exact shape the shard protocol serves.

        Deliberately whitelist-shaped rather than "does it look restore-ish":
        a false positive silently corrupts a beam prune, while a false
        negative merely costs the cluster speedup on that call.

        Four conditions, each for its own reason:

        1. No positional argument beyond ``params``. All six vendored call
           sites use keywords only, so a positional caller is a shape we have
           never seen and must not reinterpret.
        2. No non-restore kwarg present. ``output_return_emb`` changes the
           return arity; ``text_char_emb``/``padding`` are the saliency
           signature, which passes no ``text_char`` at all and is
           differentiated under ``jax.grad``.
        3. ``text_char`` present -- it is the only thing the worker protocol
           can encode (see shard_worker.py).
        4. No vision input actually in use.

        Condition 2 is checked before condition 4 on purpose: it guarantees
        ``_vision_in_use`` can never be handed a JAX tracer from a saliency
        call, where ``np.asarray`` would fail.
        """
        if args:
            return False
        if not _NON_RESTORE_KWARGS.isdisjoint(kwargs):
            return False
        if kwargs.get("text_char") is None:
            return False
        if kwargs.get("vision_img") is not None:
            return False
        return not _vision_in_use(kwargs.get("vision_available"))

    def __call__(self, params: Any, *args: Any, **kwargs: Any) -> Any:
        """Proxy the model's ``apply``, sharding only the restore beam batch.

        This is a *transparent proxy* first and an optimisation second. Every
        argument is forwarded untouched and, on every path except the one it
        deliberately optimises, the callee's return value is handed back
        as-is -- same object, same arity.

        That is not fastidiousness. ``forward`` is called by six vendored
        sites with three different signatures and two different return
        arities (util/eval.py:212, 436, 449, 534; eval/inference.py:266, 343),
        because ``output_return_emb`` makes the model return
        ``(outputs, torso_output)`` instead of ``outputs``
        (models/model.py:414-416). An earlier version modelled only the
        restore call and bound the rest as named parameters, which broke two
        live endpoints: contextualize received a 5-tuple where it unpacks 2,
        and attribute had its ``text_char_emb``/``padding`` replaced by the
        restore call's kwargs until ``jnp.sum(padding, 1)`` raised.

        Taking ``*args, **kwargs`` is load-bearing: named parameters bind
        arguments out of ``kwargs`` and re-pass them explicitly, turning
        "caller passed nothing" into "caller passed None". Here an argument
        the caller did not supply is simply absent.
        """
        if not self._is_shardable(args, kwargs):
            return self.local_forward(params, *args, **kwargs)

        text_char = kwargs["text_char"]
        sizes = plan_split(text_char.shape[0], self.node_count, self.min_rows_per_node)
        if len(sizes) == 1:
            # Expected on the '#' expansion tail as the beam prunes below
            # min_rows_per_node per node. Logged so that a batch-too-small
            # local pass is distinguishable from a bypass or a dead cluster.
            logger.debug(
                "Batch of %d below %d rows x %d nodes; computing locally",
                text_char.shape[0],
                self.min_rows_per_node,
                self.node_count,
            )
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

        # Success is logged too, not just failure: without this a local pass and
        # a sharded one are indistinguishable in the coordinator's logs, which is
        # what let the vision-guard bypass go unnoticed. DEBUG because it fires
        # once per generation.
        logger.debug(
            "Sharded batch of %d across %d nodes as %s",
            text_char.shape[0],
            self.node_count,
            sizes,
        )

        # Synthesising a 5-tuple is licensed here, and only here, by
        # `_is_shardable`: it guarantees `output_return_emb` was absent, so a
        # 5-tuple is exactly what the model would have returned. Only the mask
        # and unk logits are populated, which is all the restore path reads.
        mask_logits = np.concatenate([r[0] for r in results], axis=0)
        unk_logits = np.concatenate([r[1] for r in results], axis=0)
        return None, None, mask_logits, None, unk_logits

    def close(self) -> None:
        """Release the pooled HTTP connections."""
        self._client.close()
