"""Pins the model input contract (moved from src/vendor_contract_test.py)."""

from services.ithaca.alphabet import GreekAlphabet, LatinAlphabet
from services.ithaca import inference


def test_user_facing_gap_markers_are_question_mark_and_hash():
    """The notation the UI teaches must be the notation inference expects."""
    assert inference.ALPHABET_MISSING_RESTORE == "?"
    assert inference.ALPHABET_MISSING_UNK_RESTORE == "#"


def test_question_mark_is_outside_the_vocabulary_but_hyphen_is_inside():
    alphabet = GreekAlphabet()
    assert "?" not in alphabet.char2idx
    assert alphabet.char2idx["-"] == 4
    assert alphabet.missing == "-"
    assert alphabet.missing_unk == "_"
    assert alphabet.pad == "#"


def test_model_class_imports_from_new_home():
    """The Flax model must be importable without the vendor tree."""
    from services.ithaca.model.model import Model

    assert Model is not None
