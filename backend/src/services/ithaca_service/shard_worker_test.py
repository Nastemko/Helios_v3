"""The worker chunks its slice too.

Without this the cluster only parallelises on the coordinator: a worker
handed 18 rows would run them as one forward pass and leave most of its own
CPU idle, which is exactly the waste the chunking exists to remove. The
deployed worker measured 199% of a 300% allowance on a whole 35-row batch.

Exercises the real ``_run_forward`` against a stub service so the wiring is
covered, not just the helper it delegates to.
"""

from unittest.mock import patch

import numpy as np

from services.ithaca_service.distributed_forward import decode_logits, encode_batch
from services.ithaca_service.shard_worker import _run_forward


class _FakeModel:
    """Row-independent stand-in, like the real model."""

    params = {"params": {}}

    def __init__(self) -> None:
        self.seen: list[int] = []

    def forward(self, params, text_char, **kwargs):
        self.seen.append(text_char.shape[0])
        mask = text_char.astype(np.float32) * 2.0
        unk = text_char.astype(np.float32) * -3.0
        return None, None, mask, None, unk


class _FakeService:
    def __init__(self, model: _FakeModel) -> None:
        self._models = {"greek": model}


class TestWorkerChunking:
    """_run_forward splits its batch and reassembles it in order."""

    def test_chunked_result_is_bit_identical_and_ordered(self):
        model = _FakeModel()
        # Distinct per-row content so a reordering cannot go unnoticed.
        x = np.stack([np.full(199, i + 1, dtype=np.int32) for i in range(35)])

        with patch(
            "services.ithaca_service.shard_worker.get_ithaca_service",
            return_value=_FakeService(model),
        ), patch("services.ithaca_service.shard_worker.CHUNK_COUNT", 4):
            payload = _run_forward(encode_batch(x), "greek")

        got_mask, got_unk = decode_logits(payload)

        assert sorted(model.seen) == [8, 9, 9, 9]
        assert np.array_equal(got_mask, x.astype(np.float32) * 2.0)
        assert np.array_equal(got_unk, x.astype(np.float32) * -3.0)

    def test_unchunked_when_chunking_disabled(self):
        """CHUNK_COUNT of 1 keeps the original single-call path."""
        model = _FakeModel()
        x = np.random.randint(1, 25, size=(35, 199), dtype=np.int32)

        with patch(
            "services.ithaca_service.shard_worker.get_ithaca_service",
            return_value=_FakeService(model),
        ), patch("services.ithaca_service.shard_worker.CHUNK_COUNT", 1):
            payload = _run_forward(encode_batch(x), "greek")

        got_mask, _ = decode_logits(payload)

        assert model.seen == [35]
        assert np.array_equal(got_mask, x.astype(np.float32) * 2.0)
