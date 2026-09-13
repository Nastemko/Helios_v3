"""Tests for morphology service matching helpers (no CLTK models needed)"""

import unicodedata

from services.morphology import _normalize_for_match, _select_word_index


class TestNormalizeForMatch:
    def test_nfd_and_nfc_forms_match(self):
        decomposed = unicodedata.normalize("NFD", "μῆνιν")
        assert _normalize_for_match(decomposed) == _normalize_for_match("μῆνιν")

    def test_final_sigma_folds_to_medial(self):
        assert _normalize_for_match("ς") == _normalize_for_match("σ")

    def test_case_insensitive_greek(self):
        assert _normalize_for_match("ὈΔΥΣΣΕΎΣ") == _normalize_for_match("Ὀδυσσεύς")

    def test_punctuation_stripped(self):
        assert _normalize_for_match("θεά,") == _normalize_for_match("θεά")
        assert _normalize_for_match("(θεά)") == _normalize_for_match("θεά")

    def test_diacritics_not_folded(self):
        # καὶ (conjunction) and καί (adverb) are different words
        assert _normalize_for_match("καὶ") != _normalize_for_match("καί")

    def test_empty_string(self):
        assert _normalize_for_match("") == ""


class TestSelectWordIndex:
    WORDS = ["μῆνιν", "ἄειδε", "θεά", "Πηληϊάδεω", "Ἀχιλῆος"]

    def test_finds_word(self):
        assert _select_word_index(self.WORDS, "θεά") == 2

    def test_first_occurrence_default(self):
        words = ["καὶ", "λόγος", "καὶ", "πρᾶξις"]
        assert _select_word_index(words, "καὶ", 0) == 0

    def test_nth_occurrence(self):
        words = ["καὶ", "λόγος", "καὶ", "πρᾶξις"]
        assert _select_word_index(words, "καὶ", 1) == 2

    def test_occurrence_clamped_to_last(self):
        words = ["καὶ", "λόγος", "καὶ"]
        assert _select_word_index(words, "καὶ", 7) == 2

    def test_no_match_returns_none(self):
        assert _select_word_index(self.WORDS, "ξίφος") is None

    def test_target_with_punctuation_and_nfd(self):
        target = unicodedata.normalize("NFD", "θεά,")
        assert _select_word_index(self.WORDS, target) == 2
