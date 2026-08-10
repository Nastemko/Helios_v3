"""Pins the sharded forward pass against the single-process one.

Splitting the beam batch across machines is only safe if it leaves the model's
answer alone, so the central assertion here is bit-exactness: a sharded call
must return byte-identical logits to a local one, and a full beam search driven
through the wrapper must produce the same candidates in the same order.

A deterministic fake ``forward`` stands in for the checkpoint, so these run
without the 2GB of model files.
"""

import jax
import jax.numpy as jnp
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
import vendor.predictingthepast.util.eval as eval_util
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
    """Fake model mirroring the real ``Model.__call__`` contract.

    Row-independent by construction, exactly like the real model -- which is
    the property that makes sharding valid in the first place.

    It deliberately reproduces three behaviours of models/model.py that a
    simpler stub would paper over, because each one is load-bearing for a bug
    the sharding wrapper actually shipped:

    * ``output_return_emb`` changes the *arity* of the return value
      (model.py:414-416). A wrapper that builds its own tuple cannot be
      correct for both shapes.
    * ``padding`` is derived from ``text_char``/``text_char_onehot`` when
      absent, and ``jnp.sum(padding, 1)`` raises if it is still None
      (model.py:162-167). That TypeError was the attribute 500.
    * ``text_char_emb`` is a third, mutually exclusive way to supply input
      (model.py:170-177), used by the saliency losses under jax.grad.

    Calls are recorded on ``forward.received`` so tests can assert that
    arguments were forwarded faithfully rather than silently replaced.
    """
    rng = np.random.RandomState(seed)
    table = rng.randn(900, VOCAB).astype(np.float32)
    unk_table = rng.randn(900, 2).astype(np.float32)
    subregion_table = rng.randn(900, 8).astype(np.float32)
    date_table = rng.randn(900, 160).astype(np.float32)

    def forward(
        params,
        text_char=None,
        text_char_onehot=None,
        text_char_emb=None,
        padding=None,
        output_return_emb=False,
        **kwargs,
    ):
        # Mirror Flax's own validation so a caller that drops params fails here
        # rather than silently falling back to a local pass in production.
        if not isinstance(params, dict):
            raise TypeError(
                "The first argument passed to an apply function should be a "
                f"dictionary of collections, got {type(params).__name__}"
            )

        forward.received.append(
            {
                "text_char": text_char,
                "text_char_onehot": text_char_onehot,
                "text_char_emb": text_char_emb,
                "padding": padding,
                "output_return_emb": output_return_emb,
                **kwargs,
            }
        )

        # model.py:162-167. The real model dies in `jnp.sum(padding, 1)` when
        # padding could not be derived; reproducing that exact failure is the
        # point, since it is what a dropped `padding=` kwarg produces.
        if padding is None:
            if text_char is not None:
                padding = jnp.where(text_char > 0, 1, 0)
            elif text_char_onehot is not None:
                padding = jnp.where(text_char_onehot.argmax(-1) > 0, 1, 0)
        if padding is None:
            raise TypeError(
                "sum requires ndarray or scalar arguments, got "
                "<class 'NoneType'> at position 0."
            )

        # model.py:170-177: text_char | text_char_onehot | text_char_emb.
        if text_char is not None:
            batch, length = text_char.shape
            emb = None
        elif text_char_emb is not None:
            # jnp (not np) so the saliency tests can differentiate through it.
            batch, length = text_char_emb.shape[0], text_char_emb.shape[1]
            emb = text_char_emb
        else:
            raise ValueError("Wrong text_char value.")

        mask_logits = jnp.broadcast_to(table[:length], (batch, length, VOCAB))
        unk_logits = jnp.broadcast_to(unk_table[:length], (batch, length, 2))
        # Date and subregion are predicted once per sequence, not per
        # character (model.py returns them off the pooled torso output), so
        # these are 2-D. saliency_loss_date indexes them as `[0, argmax[0]]`.
        date_logits = jnp.broadcast_to(date_table[0], (batch, 160))
        subregion_logits = jnp.broadcast_to(subregion_table[0], (batch, 8))
        if emb is not None:
            # Make the outputs depend on the embedding so gradients are nonzero.
            mask_logits = mask_logits * jnp.sum(emb, axis=-1, keepdims=True)
            seq_scale = jnp.sum(emb, axis=(1, 2))[:, None]
            date_logits = date_logits * seq_scale
            subregion_logits = subregion_logits * seq_scale

        outputs = (date_logits, subregion_logits, mask_logits, None, unk_logits)
        if output_return_emb:
            # model.py:414-416 -- arity depends on an input kwarg.
            torso_output = jnp.zeros((batch, length, 4), dtype=jnp.float32)
            return outputs, torso_output
        return outputs

    forward.received = []
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

    def test_all_false_vision_available_still_shards(self):
        """An all-False mask means no vision, so it must not block sharding.

        beam_search_batch defaults vision_available to False and repeats it
        across the batch, so this is the shape every restore actually sends.
        Treating it as "vision present" disabled the cluster entirely.
        """
        _, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(35, 199), dtype=np.int32)
        # Exactly the kwargs eval.py:212 sends, so that a future addition to
        # the non-shardable kwarg set which accidentally covers a restore
        # kwarg fails here rather than silently disabling the cluster again.
        dist(
            FAKE_PARAMS,
            text_char=x,
            text_char_onehot=None,
            vision_img=None,
            vision_available=np.zeros((35,), dtype=bool),
        )
        assert sorted(shape[0] for shape in client.calls) == [11, 12]

    def test_partially_true_vision_available_bypasses(self):
        """Any real vision row is enough to make a split unsafe."""
        _, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(35, 199), dtype=np.int32)
        available = np.zeros((35,), dtype=bool)
        available[7] = True
        dist(FAKE_PARAMS, text_char=x, vision_available=available)
        assert client.calls == []


class TestNonRestoreCallSitesPassThrough:
    """The wrapper is a proxy first and an optimisation second.

    ``forward`` is called by six vendored sites with three different
    signatures and two different return arities. The shard protocol only
    speaks "token block in, mask+unk logits out", so every other shape must
    reach the local model untouched -- same kwargs, same return arity.

    An earlier version modelled only the restore call (eval.py:212), which
    broke two live endpoints: contextualize got a 5-tuple where it unpacks 2,
    and attribute had its text_char_emb/padding silently replaced.
    """

    def test_embedding_call_returns_two_tuple(self):
        """inference.py:266 unpacks exactly 2 values.

        The model returns ``(outputs, torso_output)`` when output_return_emb
        is set (model.py:414-416), so a wrapper that always builds its own
        5-tuple raises "too many values to unpack (expected 2)" -- which
        ithaca_service.contextualize catches as a ValueError and turns into a
        successful-looking HTTP 200 with zero results.
        """
        forward, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(1, 40), dtype=np.int32)

        _, torso_outputs = dist(
            FAKE_PARAMS,
            text_char=x,
            output_return_emb=True,
            rngs={"dropout": jax.random.PRNGKey(0)},
            is_training=False,
        )

        assert torso_outputs is not None
        # Embedding extraction cannot be served by the worker protocol.
        assert client.calls == []
        # The kwargs the old wrapper silently dropped must reach the model:
        # real Flax raises if a dropout layer is left without an RNG.
        seen = forward.received[-1]
        assert seen["output_return_emb"] is True
        assert "rngs" in seen and seen["is_training"] is False

    def test_attribution_call_keeps_five_tuple_and_kwargs(self):
        """inference.py:343 passes vision plus rngs/is_training, unpacks 5."""
        forward, dist, client = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(1, 40), dtype=np.int32)

        result = dist(
            FAKE_PARAMS,
            text_char=x,
            vision_img=np.zeros((1, 4, 4, 1)),
            vision_available=np.zeros((1,)),
            rngs={"dropout": jax.random.PRNGKey(0)},
            is_training=False,
        )

        assert len(result) == 5
        assert client.calls == []
        assert "rngs" in forward.received[-1]

    @pytest.mark.parametrize(
        "loss_fn,extra",
        [
            ("saliency_loss_subregion", {}),
            ("saliency_loss_date", {}),
            ("saliency_loss_mask", {"char_pos": 3, "char_idx": 2}),
        ],
    )
    def test_saliency_calls_receive_their_own_kwargs(self, loss_fn, extra):
        """eval.py:436/449/534 pass text_char_emb+padding and NO text_char.

        The old wrapper saw ``text_char is None``, took its bypass, and called
        _call_local -- which hardcodes the five restore kwargs and drops
        text_char_emb and padding entirely. padding=None then reached
        `jnp.sum(padding, 1)` in model.py:167 and the request 500'd.

        Driven through the real vendored functions so this breaks if their
        signatures ever change.
        """
        forward, dist, client = _make_distributed(shard_count=2)
        emb = jnp.asarray(np.random.randn(1, 20, 4).astype(np.float32))
        padding = jnp.ones((1, 20), dtype=jnp.int32)

        getattr(eval_util, loss_fn)(dist, FAKE_PARAMS, emb, padding, **extra)

        assert client.calls == []
        seen = forward.received[-1]
        assert seen["text_char_emb"] is emb, "text_char_emb was dropped"
        assert seen["padding"] is padding, "padding was dropped"
        assert seen["text_char"] is None

    def test_saliency_works_under_jax_grad(self):
        """The saliency losses are differentiated, not just called.

        eval.py:497-502 wraps them in jax.grad, so the wrapper sees tracers
        rather than concrete arrays. Any np.asarray or .shape[0] evaluated on
        the passthrough path would fail here even though the plain calls
        above succeed -- which is why the shardability decision must be made
        before any numpy coercion.
        """
        _, dist, _ = _make_distributed(shard_count=2)
        emb = jnp.asarray(np.random.randn(1, 20, 4).astype(np.float32))
        padding = jnp.ones((1, 20), dtype=jnp.int32)

        grad = jax.grad(eval_util.saliency_loss_date, 2)(
            dist, FAKE_PARAMS, emb, padding
        )

        assert grad.shape == emb.shape

    def test_unknown_kwargs_are_forwarded(self):
        """The proxy must not enumerate the model's parameter list.

        Flax's ``apply`` also accepts mutable/method/capture_intermediates; a
        wrapper that binds a fixed set of names silently drops them.
        """
        forward, dist, _ = _make_distributed(shard_count=2)
        x = np.random.randint(1, VOCAB, size=(1, 40), dtype=np.int32)

        dist(FAKE_PARAMS, text_char=x, padding=None, capture_intermediates=True)

        assert forward.received[-1]["capture_intermediates"] is True


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

    def test_search_actually_reaches_the_workers(self):
        """The bit-exactness test above passes even if nothing is distributed.

        A wrapper that silently runs every generation locally returns exactly
        the right answer, so equality cannot detect it -- and that is precisely
        how a bypass shipped: `beam_search_batch` defaults `vision_available`
        to `False`, not `None`, so it forwards an all-False array that a
        `is not None` guard reads as "vision in use". Assert the round trips
        happened rather than just that the answer is right.
        """
        _, dist, client = _make_distributed(shard_count=2)
        self._search(self.CASES["single_gap"], dist)

        assert client.calls, "no slice ever left the coordinator"
        # Two workers per fanned-out generation. Batch size varies across
        # generations (the first starts from a single seed entry, and the beam
        # prunes later), so assert the pairing rather than specific row counts.
        assert len(client.calls) % 2 == 0
        # Every shipped slice must be a strict subset of the beam, or the
        # coordinator sent the whole batch out and kept no work for itself.
        assert all(shape[0] < 35 for shape in client.calls)
