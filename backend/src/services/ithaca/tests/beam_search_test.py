"""Pins beam-search behavior (moved from src/vendor_beam_search_test.py)."""

import numpy as np

from services.ithaca.alphabet import GreekAlphabet
from services.ithaca.beam_search import beam_search_batch

ALPHABET = GreekAlphabet()
VOCAB = len(ALPHABET.idx2char)


def _make_forward(seed: int = 0):
    rng = np.random.RandomState(seed)
    table = rng.randn(800, VOCAB).astype(np.float32)
    unk_table = rng.randn(800, 2).astype(np.float32)

    def forward(params, text_char=None, **kwargs):
        batch, length = text_char.shape
        mask_logits = np.broadcast_to(table[:length], (batch, length, VOCAB)).copy()
        unk_logits = np.broadcast_to(unk_table[:length], (batch, length, 2)).copy()
        return None, None, mask_logits, None, unk_logits

    return forward


def test_disabling_history_does_not_change_results():
    text = "εδοξεν τηι βουληι και τωι δημωι ????? αθηναιων"
    text_sos = ALPHABET.sos + text
    mask_idx = [i for i, c in enumerate(text_sos) if c in ("?", "#")]
    padded = text_sos.replace("?", ALPHABET.missing).replace("#", ALPHABET.missing_unk)

    def _search(track_history):
        return beam_search_batch(
            _make_forward(),
            None,
            ALPHABET,
            padded,
            mask_idx,
            beam_width=20,
            sequential_decoding=False,
            max_len=len(text_sos) + 20,
            max_iterations=25,
            top_chars=None,
            track_history=track_history,
        )

    upstream = _search(True)
    without = _search(False)
    assert [e.text_pred for e in upstream] == [e.text_pred for e in without]
    assert [e.pred_logprob for e in upstream] == [e.pred_logprob for e in without]
