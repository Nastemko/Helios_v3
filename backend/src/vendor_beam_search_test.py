"""Pins the local beam-search optimizations against upstream behaviour.

`beam_search_batch` is vendored DeepMind code that we normally leave alone, but
a production request took 947s in it, so two knobs were added locally:

  - ``track_history``: upstream copies each candidate's full text trajectory on
    every expansion. Only ``sequential_restoration_saliency`` reads it, and that
    has no callers -- ``restore`` hardcodes ``prediction_saliency = []``.
  - ``top_chars``: upstream builds a string, a join and a set copy for all 29
    Greek branches at every hole, though only a handful survive pruning.

Both are only safe if they leave the model's answer alone, which is what these
tests assert. A deterministic fake ``forward`` stands in for the checkpoint, so
they run without the 2GB of model files.
"""

import numpy as np
import pytest

from vendor.predictingthepast.util.alphabet import GreekAlphabet
from vendor.predictingthepast.util.eval import beam_search_batch

ALPHABET = GreekAlphabet()
VOCAB = len(ALPHABET.idx2char)

# Each case is exercised through the same path restore() uses
# (sequential_decoding=False), including the '#' expansion branch.
CASES = {
    "single_gap": "εδοξεν τηι βουληι και τωι δημωι ????? αθηναιων",
    "multi_gap": "αγαθηι τυχηι δεδοχθαι τηι βουληι ??? και τωι ??? δημωι",
    "unknown_length_gap": "εδοξεν τηι βουληι και τωι δημωι # αθηναιων",
}


def _make_forward(seed: int = 0):
    """A fake model returning fixed pseudo-random logits per (position, char).

    Deterministic across calls, so two searches over the same text are
    comparable -- which is the whole point of these tests.
    """
    rng = np.random.RandomState(seed)
    table = rng.randn(800, VOCAB).astype(np.float32)
    unk_table = rng.randn(800, 2).astype(np.float32)

    def forward(params, text_char=None, **kwargs):
        batch, length = text_char.shape
        mask_logits = np.broadcast_to(table[:length], (batch, length, VOCAB)).copy()
        unk_logits = np.broadcast_to(unk_table[:length], (batch, length, 2)).copy()
        return None, None, mask_logits, None, unk_logits

    return forward


def _search(text: str, top_chars, track_history, beam_width: int = 20):
    text_sos = ALPHABET.sos + text
    mask_idx = [i for i, c in enumerate(text_sos) if c in ("?", "#")]
    padded = text_sos.replace("?", ALPHABET.missing).replace("#", ALPHABET.missing_unk)
    return beam_search_batch(
        _make_forward(),
        None,
        ALPHABET,
        padded,
        mask_idx,
        beam_width=beam_width,
        sequential_decoding=False,
        max_len=len(text_sos) + 20,
        max_iterations=25,
        top_chars=top_chars,
        track_history=track_history,
    )


@pytest.mark.parametrize("name", sorted(CASES))
def test_disabling_history_does_not_change_results(name):
    """track_history is pure bookkeeping; results must be bit-identical."""
    text = CASES[name]
    upstream = _search(text, top_chars=None, track_history=True)
    without = _search(text, top_chars=None, track_history=False)

    assert [e.text_pred for e in upstream] == [e.text_pred for e in without]
    assert [e.pred_logprob for e in upstream] == [e.pred_logprob for e in without]


@pytest.mark.parametrize("name", sorted(CASES))
def test_history_is_empty_when_not_tracked(name):
    """The point of the flag: no per-candidate list copies are retained."""
    for entry in _search(CASES[name], top_chars=None, track_history=False):
        assert len(entry.text_history) == 0


@pytest.mark.parametrize("name", sorted(CASES))
def test_top_chars_pruning_preserves_the_top_prediction(name):
    """The answer users see must not change when low-logprob branches are cut."""
    text = CASES[name]
    upstream = _search(text, top_chars=None, track_history=False)
    pruned = _search(text, top_chars=8, track_history=False)

    assert pruned, "pruning must not empty the beam"
    assert upstream[0].text_pred == pruned[0].text_pred


@pytest.mark.parametrize("name", sorted(CASES))
def test_top_chars_pruning_preserves_the_leading_candidates(name):
    """Not just top-1: the visible candidate list should be stable too."""
    text = CASES[name]
    upstream = {e.text_pred for e in _search(text, None, False)[:5]}
    pruned = {e.text_pred for e in _search(text, 8, False)[:5]}

    assert upstream == pruned


def test_max_iterations_bounds_the_search():
    """The runaway guard: '#' expansion must stop at the supplied bound."""
    text = CASES["unknown_length_gap"]
    text_sos = ALPHABET.sos + text
    mask_idx = [i for i, c in enumerate(text_sos) if c in ("?", "#")]
    padded = text_sos.replace("?", ALPHABET.missing).replace("#", ALPHABET.missing_unk)

    # A '#' may expand one character per iteration, so a tight bound must cap
    # how long the restored gap can grow -- proving the loop actually stops.
    capped = beam_search_batch(
        _make_forward(),
        None,
        ALPHABET,
        padded,
        mask_idx,
        beam_width=20,
        sequential_decoding=False,
        max_len=len(text_sos) + 20,
        max_iterations=3,
        top_chars=8,
    )
    assert capped, "a bounded search should still return its best candidates"
    assert max(e.unk_len for e in capped) <= 3
