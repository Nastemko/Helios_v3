"""Pins the vendored model's input contract.

`vendor/predictingthepast/` is upstream DeepMind code that we do not modify, so
the only way to notice a breaking change on re-sync is to assert the facts our
own code depends on. Every assertion here corresponds to a decision made in
routers/inscriptions.py or the workbench UI.

The central fact, and the one that caused the original bug: there are two
character sets, and they do not agree.

  - user-facing:  '?' = one missing character, '#' = unknown-length gap
  - model vocab:  '-' = missing, '_' = missing_unk, '#' = padding

`_prepare_text` records the positions of '?'/'#' into restore_mask_idx *and
then* rewrites them to '-'/'_'. So '?' is what marks a hole for beam search,
while '-' is only what the model reads once the hole has been marked.
"""

import re
import unicodedata

import pytest

from vendor.predictingthepast.eval import inference
from vendor.predictingthepast.util.alphabet import GreekAlphabet, LatinAlphabet

# The examples offered by the "Show me an example" dropdown in
# frontend/src/components/inscription/InscriptionInput.tsx. An example that is
# out of alphabet or under the length minimum is a guaranteed user-visible
# failure, so they are checked against the real model contract here.
GREEK_UI_EXAMPLES = [
    "εδοξεν τηι βουληι και τωι δημωι λυσιστρατος ειπε επειδη διοφανης ανηρ "
    "αγαθος ων διατελει περι δηλιους δεδοχθαι τωι ????? διοφανην καλλι???????? "
    "??ηναιον προξενον ειναι δ????????? αυτογ και εκγονους κ?? ειναι αυτοις "
    "ατελειαν εν δηλωι παντων και γης και οικιας εγκτησιν και προσοδον προς "
    "τημ βουλην και τον δημον πρωτοις μετα τα ιερα και τα αλλα οσα και τοις "
    "αλλοις προξενοις και ευεργεταις του ιερου δεδοται",
    "ευψυχι αλεξανδρε ουδεις αθανατος",
    "φιλεταιρος ευμενου περγαμευς μουσαις καφισιας εποιησε",
    "βασιλευοντος τολεμαιου του τολεμαιου ετους ενδεκατου μηνος περειτιου "
    "εκκλησιας κυριας γενομενης εδοξε # τωι δημωι",
]

LATIN_UI_EXAMPLES = [
    "imp caesar divi # f augustus pontifex maximus tribunicia potestate ????? "
    "cos xiii pater patriae",
    "dis manibus sacrum gaius iulius maximus vixit annis lx mensibus iii "
    "diebus x hic situs est sit tibi terra levis",
    "iovi optimo maximo sacrum pro salute imperatoris caesaris traiani "
    "hadriani augusti",
    "senatus populusque romanus # restituit",
]


def _normalize(text: str) -> str:
    """Reproduce the normalization _prepare_text applies before validating."""
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return "".join(
        c
        for c in unicodedata.normalize("NFD", collapsed)
        if unicodedata.category(c) != "Mn"
    )


def test_user_facing_gap_markers_are_question_mark_and_hash():
    """The notation the UI teaches must be the notation inference expects."""
    assert inference.ALPHABET_MISSING_RESTORE == "?"
    assert inference.ALPHABET_MISSING_UNK_RESTORE == "#"


@pytest.mark.parametrize("alphabet_cls", [GreekAlphabet, LatinAlphabet])
def test_question_mark_is_outside_the_vocabulary_but_hyphen_is_inside(alphabet_cls):
    """The inversion that makes '?' the correct user-facing marker.

    '?' works precisely because it cannot occur in real text, so the scan for
    holes is unambiguous. '-' is a vocabulary token and therefore cannot serve
    that role.
    """
    alphabet = alphabet_cls()

    assert "?" not in alphabet.char2idx
    assert alphabet.char2idx["-"] == 4
    assert alphabet.missing == "-"
    assert alphabet.missing_unk == "_"
    assert alphabet.pad == "#"


def test_question_marks_become_fillable_holes():
    """'?' populates restore_mask_idx and is handed to the model as '-'."""
    text = "εδοξεν τηι βουληι και τωι δημωι ????? αθηναιων"

    _, text_sos, text_padded, _, _, _, restore_mask_idx = inference._prepare_text(
        text, GreekAlphabet()
    )

    assert len(restore_mask_idx) == 5
    # Contiguous run, and offset by one for the prepended SOS symbol.
    assert restore_mask_idx == list(range(text_sos.index("?"), text_sos.index("?") + 5))
    assert "?" not in text_padded
    assert "-----" in text_padded


def test_hyphens_are_silently_unfillable():
    """A '-' reaches the model but is never scheduled for restoration.

    This is why the API rejects it rather than passing it through: the failure
    mode is a no-op that looks exactly like a successful restoration.
    """
    text = "εδοξεν τηι βουληι και τωι δημωι ----- αθηναιων"

    _, _, text_padded, _, _, _, restore_mask_idx = inference._prepare_text(
        text, GreekAlphabet()
    )

    assert restore_mask_idx == []
    # Identical model input to the '?????' case above, yet nothing gets filled.
    assert "-----" in text_padded


def test_restore_requires_at_least_one_gap_marker():
    """Hyphen-only input does not count as having gaps."""
    text = "εδοξεν τηι βουληι και τωι δημωι ----- αθηναιων"

    with pytest.raises(ValueError, match="At least one character must be missing"):
        inference.restore(
            text,
            forward=None,
            params=None,
            alphabet=GreekAlphabet(),
            vocab_char_size=35,
        )


def test_minimum_text_length_is_twenty_five():
    """The UI's character counter advertises this bound, so pin it."""
    assert inference.MIN_TEXT_LEN == 25

    with pytest.raises(ValueError, match="too short"):
        inference._prepare_text("εδοξεν ?", GreekAlphabet())


def test_unknown_length_restoration_ceiling_is_twenty():
    """RestoreRequest.max_restoration_len is bounded by this value."""
    assert inference.UNK_RESTORATION_MAX_LEN == 20


@pytest.mark.parametrize(
    "text,alphabet_cls",
    [(t, GreekAlphabet) for t in GREEK_UI_EXAMPLES]
    + [(t, LatinAlphabet) for t in LATIN_UI_EXAMPLES],
)
def test_ui_examples_satisfy_the_model_contract(text, alphabet_cls):
    """Every built-in example must be loadable without erroring.

    Out-of-alphabet characters raise KeyError inside the tokenizer, and the
    Latin alphabet in particular has no 'j' or 'w'.
    """
    normalized = _normalize(text)

    assert "-" not in text, "UI examples must use '?' notation"
    assert len(normalized) >= inference.MIN_TEXT_LEN

    # Does not raise: every character is in the vocabulary.
    inference._prepare_text(text, alphabet_cls())
