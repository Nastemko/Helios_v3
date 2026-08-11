"""Pins threaded chunking against the unchunked forward pass.

The forward pass leaves roughly half of each node's CPU idle (measured 280%
of 600% on the coordinator), and splitting one batch across threads recovers
it -- 1.80x on a 35-row batch. That is only safe because rows are independent
through the model, so the assertion that matters here is the same one the
cross-machine sharding rests on: chunked output must be bit-identical to
unchunked, in the original row order.
"""

import numpy as np
import pytest

from services.ithaca_service.chunked_forward import (
    chunked_forward,
    plan_chunks,
    resolve_chunk_count,
)


def _run(text_char: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Row-independent stand-in for the model, like the real forward pass."""
    mask = text_char.astype(np.float32) * 2.0
    unk = text_char.astype(np.float32) * -3.0
    return mask, unk


class TestPlanChunks:
    """Row distribution across threads."""

    def test_remainder_goes_to_earliest_chunks(self):
        assert plan_chunks(35, 4, 4) == [9, 9, 9, 8]

    def test_even_split(self):
        assert plan_chunks(36, 4, 4) == [9, 9, 9, 9]

    def test_stays_whole_when_chunks_too_small(self):
        """Thread overhead is not repaid on tiny slices."""
        assert plan_chunks(6, 4, 4) == [6]

    def test_single_chunk_never_splits(self):
        assert plan_chunks(35, 1, 4) == [35]


class TestChunkedMatchesUnchunked:
    """The property that makes chunking safe."""

    @pytest.mark.parametrize("batch", [35, 36, 12, 20])
    def test_chunked_logits_are_bit_identical(self, batch):
        x = np.random.randint(1, 25, size=(batch, 199), dtype=np.int32)
        want_mask, want_unk = _run(x)

        got_mask, got_unk = chunked_forward(
            _run, x, chunk_count=4, min_rows_per_chunk=4
        )

        assert np.array_equal(got_mask, want_mask)
        assert np.array_equal(got_unk, want_unk)

    def test_rows_are_reassembled_in_original_order(self):
        """Threads finish out of order; a transposition would be silent."""
        x = np.stack([np.full(199, i + 1, dtype=np.int32) for i in range(35)])
        want_mask, _ = _run(x)

        got_mask, _ = chunked_forward(_run, x, chunk_count=4, min_rows_per_chunk=4)

        for row in range(35):
            assert np.array_equal(got_mask[row], want_mask[row]), f"row {row} misplaced"

    def test_work_is_actually_chunked(self):
        """Guard against silently degrading to one whole-batch call."""
        seen: list[int] = []

        def recording(text_char: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            seen.append(text_char.shape[0])
            return _run(text_char)

        x = np.random.randint(1, 25, size=(35, 199), dtype=np.int32)
        chunked_forward(recording, x, chunk_count=4, min_rows_per_chunk=4)

        assert sorted(seen) == [8, 9, 9, 9]

    def test_small_batch_runs_in_one_call(self):
        seen: list[int] = []

        def recording(text_char: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            seen.append(text_char.shape[0])
            return _run(text_char)

        x = np.random.randint(1, 25, size=(6, 199), dtype=np.int32)
        chunked_forward(recording, x, chunk_count=4, min_rows_per_chunk=4)

        assert seen == [6]

    def test_chunk_error_propagates(self):
        """A failure inside a thread must not be swallowed into a wrong answer."""

        def boom(text_char: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            raise RuntimeError("model exploded")

        x = np.random.randint(1, 25, size=(35, 199), dtype=np.int32)
        with pytest.raises(RuntimeError, match="model exploded"):
            chunked_forward(boom, x, chunk_count=4, min_rows_per_chunk=4)


class TestResolveChunkCount:
    """Explicit configuration beats autodetection."""

    def test_positive_value_is_respected(self):
        assert resolve_chunk_count(3) == 3

    def test_zero_autodetects(self):
        assert resolve_chunk_count(0) >= 1

    def test_negative_autodetects(self):
        assert resolve_chunk_count(-1) >= 1
