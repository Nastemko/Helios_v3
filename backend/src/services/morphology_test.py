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


from services.morphology import MorphologyService


class _FakeFeature:
    def __init__(self, key: str, value_label: str) -> None:
        self.key = key
        self.value_label = value_label


class _FakeFeatureSet:
    def __init__(self, features) -> None:
        self.features = features


class _FakeWord:
    def __init__(self, string, lemma, upos, features=None) -> None:
        self.string = string
        self.lemma = lemma
        self.upos = upos
        self.features = features


class TestBuildAnalysis:
    def _service(self) -> MorphologyService:
        # Skip __init__ (downloads CLTK models)
        return object.__new__(MorphologyService)

    def test_extracts_lemma_pos_and_morphology(self):
        svc = self._service()
        w = _FakeWord(
            "μῆνιν",
            "μῆνις",
            "NOUN",
            _FakeFeatureSet(
                [
                    _FakeFeature("Case", "Accusative"),
                    _FakeFeature("Number", "Singular"),
                    _FakeFeature("Gender", "Feminine"),
                ]
            ),
        )
        result = svc._build_analysis(w, "μῆνιν", "grc")
        assert result["lemma"] == "μῆνις"
        assert result["pos"] == "Noun"
        assert result["morphology"]["case"] == "Accusative"
        assert result["morphology"]["number"] == "Singular"
        assert result["language"] == "grc"

    def test_falls_back_to_word_when_lemma_missing(self):
        svc = self._service()
        w = _FakeWord("ξίφος", None, None, None)
        result = svc._build_analysis(w, "ξίφος", "lat")
        assert result["lemma"] == "ξίφος"
        assert result["pos"] == "Unknown"
        assert result["language"] == "lat"
