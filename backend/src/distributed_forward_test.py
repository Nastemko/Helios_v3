"""Pins the sharded forward pass against the single-process one.

Splitting the beam batch across machines is only safe if it leaves the model's
answer alone, so the central assertion here is bit-exactness: a sharded call
must return byte-identical logits to a local one, and a full beam search driven
through the wrapper must produce the same candidates in the same order.

A deterministic fake ``forward`` stands in for the checkpoint, so these run
without the 2GB of model files.
"""

import numpy as np
import pytest

from services.ithaca_service.distributed_forward import (
    DistributedForward,
    decode_batch,
    decode_logits,
    encode_batch,
    encode_logits,
    plan_split,
)
from vendor.predictingthepast.util.alphabet import GreekAlphabet
from vendor.predictingthepast.util.eval import beam_search_batch

ALPHABET = GreekAlphabet()
VOCAB = len(ALPHABET.idx2char)


# Stands in for a Flax params pytree. The real `model.apply` rejects anything
# that is not a dict of collections, so the fake below enforces the same
# contract -- an earlier version ignored `params` entirely and hid a bug where
# the coordinator's local slice was called without them.
FAKE_PARAMS = {"params": {"dense": {"kernel": np.zeros((2, 2), dtype=np.float32)}}}


def _make_forward(seed: int = 0):
    """Fake model: fixed pseudo-random logits per (position, char).

    Row-independent by construction, exactly like the real model -- which is
    the property that makes sharding valid in the first place.
    """
    rng = np.random.RandomState(seed)
    table = rng.randn(900, VOCAB).astype(np.float32)
    unk_table = rng.randn(900, 2).astype(np.float32)

    def forward(params, text_char=None, **kwargs):
        # Mirror Flax's own validation so a caller that drops params fails here
        # rather than silently falling back to a local pass in production.
        if not isinstance(params, dict):
            raise TypeError(
                "The first argument passed to an apply function should be a "
                f"dictionary of collections, got {type(params).__name__}"
            )
        batch, length = text_char.shape
        mask_logits = np.broadcast_to(table[:length], (batch, length, VOCAB)).copy()
        unk_logits = np.broadcast_to(unk_table[:length], (batch, length, 2)).copy()
        return None, None, mask_logits, None, unk_logits

    return forward


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _LoopbackClient:
    """Stands in for httpx, running the 'remote' slice in-process.

    Records each slice's shape so tests can assert how work was divided.
    """

    def __init__(self, forward, fail: bool = False):
        self.forward = forward
        self.fail = fail
        self.calls: list[tuple[int, int]] = []

    def post(self, url, content=None, headers=None, params=None):
        if self.fail:
            raise ConnectionError("shard down")
        text_char = decode_batch(content)
        self.calls.append(text_char.shape)
        _, _, mask_logits, _, unk_logits = self.forward(
            FAKE_PARAMS, text_char=text_char
        )
        return _FakeResponse(encode_logits(mask_logits, unk_logits))

    def close(self) -> None:
        pass


def _make_distributed(shard_count: int, fail: bool = False, min_rows: int = 4):
    forward = _make_forward()
    dist = DistributedForward(
        local_forward=forward,
        shard_urls=[f"http://shard{i}" for i in range(shard_count)],
        language="greek",
        min_rows_per_node=min_rows,
    )
    client = _LoopbackClient(forward, fail=fail)
    dist._client = client
    return forward, dist, client


class TestPlanSplit:
    """Row distribution across nodes."""

    def test_beam_35_over_3_nodes(self):
        """Remainder goes to the earliest nodes."""
        assert plan_split(35, 3, 4) == [12, 12, 11]

    def test_even_split(self):
        assert plan_split(36, 3, 4) == [12, 12, 12]

    def test_stays_local_when_slices_too_small(self):
        """Below the threshold a round trip costs more than it saves.

        Per-row cost is flat down to batch 4 but collapses under it, so the
        '#' expansion tail must not be sharded.
        """
        assert plan_split(9, 3, 4) == [9]
        assert plan_split(11, 3, 4) == [11]
        # 12 is the smallest batch that still gives every node 4 rows.
        assert plan_split(12, 3, 4) == [4, 4, 4]

    def test_single_node_never_splits(self):
        assert plan_split(35, 1, 4) == [35]


class TestCodecs:
    """Wire format round-trips."""

    def test_batch_round_trip(self):
        batch = np.random.randint(0, 30, size=(12, 199), dtype=np.int32)
        assert np.array_equal(decode_batch(encode_batch(batch)), batch)

    def test_logits_round_trip_is_exact(self):
        mask = np.random.randn(12, 199, VOCAB).astype(np.float32)
        unk = np.random.randn(12, 199, 2).astype(np.float32)
        got_mask, got_unk = decode_logits(encode_logits(mask, unk))
        assert np.array_equal(got_mask, mask)
        assert np.array_equal(got_unk, unk)


class TestShardedForwardMatchesLocal:
    """The property the whole design rests on."""

    @pytest.mark.parametrize("batch", [35, 36, 12, 20])
    def test_sharded_logits_are_bit_identical(self, batch):
        """Any drift here would silently change which candidates survive."""
        forward, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(batch, 199), dtype=np.int32)

        _, _, want_mask, _, want_unk = forward(FAKE_PARAMS, text_char=x)
        _, _, got_mask, _, got_unk = dist(FAKE_PARAMS, text_char=x)

        assert np.array_equal(got_mask, want_mask)
        assert np.array_equal(got_unk, want_unk)

    def test_rows_are_reassembled_in_original_order(self):
        """beam_batch indexes these rows positionally.

        A transposition would not raise -- it would quietly corrupt
        predictions -- so assert row-by-row rather than on aggregate shape.
        """
        forward, dist, _ = _make_distributed(shard_count=2)
        # Distinct per-row content so a reordering cannot go unnoticed.
        x = np.stack(
            [np.full(199, i % (VOCAB - 1) + 1, dtype=np.int32) for i in range(35)]
        )

        _, _, want_mask, _, _ = forward(FAKE_PARAMS, text_char=x)
        _, _, got_mask, _, _ = dist(FAKE_PARAMS, text_char=x)

        for row in range(35):
            assert np.array_equal(got_mask[row], want_mask[row]), f"row {row} misplaced"

    def test_work_is_actually_distributed(self):
        """Guard against a wrapper that silently degrades to local-only."""
        _, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(35, 199), dtype=np.int32)
        dist(FAKE_PARAMS, text_char=x)

        # Coordinator keeps 12; the two workers take 12 and 11.
        assert sorted(shape[0] for shape in client.calls) == [11, 12]

    def test_small_batch_is_not_sharded(self):
        _, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(6, 199), dtype=np.int32)
        dist(FAKE_PARAMS, text_char=x)
        assert client.calls == []


class TestFallback:
    """A dead node must degrade latency, not fail the request."""

    def test_falls_back_to_local_on_shard_failure(self):
        forward, dist, _ = _make_distributed(shard_count=2, fail=True)
        x = np.random.randint(1, VOCAB, size=(35, 199), dtype=np.int32)

        _, _, want_mask, _, want_unk = forward(FAKE_PARAMS, text_char=x)
        _, _, got_mask, _, got_unk = dist(FAKE_PARAMS, text_char=x)

        assert np.array_equal(got_mask, want_mask)
        assert np.array_equal(got_unk, want_unk)

    def test_vision_inputs_bypass_sharding(self):
        """Vision is broadcast per batch element and would need slicing too.

        restore() never sends it, but mis-sharding it would be silent, so the
        wrapper must hand those calls straight to the local model.
        """
        _, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(35, 199), dtype=np.int32)
        dist(
            FAKE_PARAMS, text_char=x, vision_img=np.zeros((1, 4)), vision_available=True
        )
        assert client.calls == []


class TestBeamSearchEndToEnd:
    """The real integration: drive a full search through the wrapper."""

    CASES = {
        "single_gap": "εδοξεν τηι βουληι και τωι δημωι ????? αθηναιων",
        "unknown_length_gap": "εδοξεν τηι βουληι και τωι δημωι # αθηναιων",
        "multi_gap": "αγαθηι τυχηι δεδοχθαι τηι βουληι ??? και τωι ??? δημωι",
    }

    def _search(self, text: str, forward, beam_width: int = 35):
        text_sos = ALPHABET.sos + text
        mask_idx = [i for i, c in enumerate(text_sos) if c in ("?", "#")]
        padded = text_sos.replace("?", ALPHABET.missing).replace(
            "#", ALPHABET.missing_unk
        )
        return beam_search_batch(
            forward,
            FAKE_PARAMS,
            ALPHABET,
            padded,
            mask_idx,
            beam_width=beam_width,
            sequential_decoding=False,
            max_len=len(text_sos) + 15,
            max_iterations=25,
            top_chars=8,
            track_history=False,
        )

    @pytest.mark.parametrize("name", sorted(CASES))
    def test_sharded_search_matches_local_search(self, name):
        """Predictions and their order must be unchanged end to end."""
        forward, dist, _ = _make_distributed(shard_count=2)

        local = self._search(self.CASES[name], forward)
        sharded = self._search(self.CASES[name], dist)

        assert [e.text_pred for e in sharded] == [e.text_pred for e in local]
        assert [e.pred_logprob for e in sharded] == [e.pred_logprob for e in local]
