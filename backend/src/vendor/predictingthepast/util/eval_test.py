"""Tests for beam-search shape bucketing.

The jitted forward pass is compiled for one (batch, seqlen) pair. Beam search
must therefore pad every call to fixed buckets, and must slice the padding back
off before the results are used, so predictions are bit-identical to the
unbucketed implementation.
"""

import unittest

import numpy as np

from vendor.predictingthepast.util import alphabet as util_alphabet
from vendor.predictingthepast.util.eval import beam_search_batch

BUCKET_SEQLEN = 768


class _RecordingForward:
    """Stands in for the model: records call shapes, returns deterministic logits."""

    def __init__(self, vocab_size: int):
        self.vocab_size = vocab_size
        self.shapes: list[tuple[int, int]] = []

    def __call__(self, params, text_char=None, **kwargs):
        self.shapes.append(tuple(text_char.shape))
        batch, seqlen = text_char.shape
        # Deterministic, position-dependent logits: seeded per call so the same
        # logical input always yields the same scores regardless of padding.
        rng = np.random.default_rng(1234)
        mask_logits = rng.random((batch, seqlen, self.vocab_size)).astype(np.float32)
        unk_logits = rng.random((batch, seqlen, 2)).astype(np.float32)
        return None, None, mask_logits, None, unk_logits


def _make_input(alphabet, n_missing: int = 2) -> tuple[str, list[int]]:
    """Build a padded text with `n_missing` gaps, as _prepare_text would."""
    text = (
        alphabet.sos + "εδοξεν τηι βουληι " + alphabet.missing * n_missing + " αθηναιων"
    )
    mask_idx = [i for i, c in enumerate(text) if c == alphabet.missing]
    padded = text + alphabet.pad * (BUCKET_SEQLEN - len(text))
    return padded, mask_idx


class TestBeamSearchShapeBucketing(unittest.TestCase):
    """forward() must always receive the same padded shape."""

    def test_forward_always_receives_bucketed_shape(self):
        alphabet = util_alphabet.GreekAlphabet()
        forward = _RecordingForward(len(alphabet.idx2char))
        padded, mask_idx = _make_input(alphabet)

        beam_search_batch(
            forward,
            {},
            alphabet,
            padded,
            mask_idx,
            beam_width=8,
            max_len=BUCKET_SEQLEN,
        )

        self.assertTrue(forward.shapes, "forward was never called")
        self.assertEqual(
            set(forward.shapes),
            {(8, BUCKET_SEQLEN)},
            f"expected every call bucketed to (8, {BUCKET_SEQLEN}), "
            f"saw {sorted(set(forward.shapes))}",
        )

    def test_bucket_is_independent_of_max_len(self):
        """max_len is derived from input length, so it must not set the bucket.

        inference.restore passes max_len = text_len (or text_len + unk budget),
        which differs per request. Bucketing on it would compile a separate XLA
        executable per input length and defeat the cache -- the exact bug this
        guards against.
        """
        alphabet = util_alphabet.GreekAlphabet()
        shapes_by_max_len = {}

        for max_len in (40, 60, BUCKET_SEQLEN):
            forward = _RecordingForward(len(alphabet.idx2char))
            padded, mask_idx = _make_input(alphabet)
            beam_search_batch(
                forward,
                {},
                alphabet,
                padded,
                mask_idx,
                beam_width=4,
                max_len=max_len,
            )
            shapes_by_max_len[max_len] = set(forward.shapes)

        distinct = set()
        for shapes in shapes_by_max_len.values():
            distinct |= shapes
        self.assertEqual(
            distinct,
            {(4, BUCKET_SEQLEN)},
            f"bucket shape varied with max_len: {shapes_by_max_len}",
        )

    def test_pad_index_is_zero(self):
        """Bucketing pads with integer 0; the model masks on `text_char > 0`.

        If pad were ever a nonzero index, padded positions would participate in
        attention and silently corrupt predictions.
        """
        for alphabet in (util_alphabet.GreekAlphabet(), util_alphabet.LatinAlphabet()):
            self.assertEqual(alphabet.pad_idx, 0, f"{type(alphabet).__name__} pad_idx")


if __name__ == "__main__":
    unittest.main()
