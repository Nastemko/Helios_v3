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


import unittest


class _FakeDoc:
    def __init__(self, words) -> None:
        self.words = words


class _FakeNLP:
    """Records analyze() calls; returns queued docs in order"""

    def __init__(self, docs) -> None:
        self.queued = list(docs)
        self.calls: list[str] = []

    def analyze(self, text: str):
        self.calls.append(text)
        return self.queued.pop(0)


class TestContextFlow(unittest.IsolatedAsyncioTestCase):
    def _svc(self, greek) -> MorphologyService:
        svc = object.__new__(MorphologyService)
        svc.greek_nlp = greek
        svc.latin_nlp = None
        svc.initialized = True
        return svc

    async def test_context_sent_analyzes_context_and_matches_word(self):
        doc = _FakeDoc(
            [
                _FakeWord("μῆνιν", "μῆνις", "NOUN"),
                _FakeWord("ἄειδε", "ἄειδε", "VERB"),
                _FakeWord("θεά", "θεά", "NOUN"),
            ]
        )
        nlp = _FakeNLP([doc])
        svc = self._svc(nlp)
        result = await svc.analyze_word("θεά", "grc", context="μῆνιν ἄειδε θεά")
        assert nlp.calls == ["μῆνιν ἄειδε θεά"]
        assert result["lemma"] == "θεά"

    async def test_second_occurrence_selected(self):
        doc = _FakeDoc(
            [
                _FakeWord("καὶ", "καί", "CCONJ"),
                _FakeWord("λόγος", "λόγος", "NOUN"),
                _FakeWord("καὶ", "καί", "ADV"),
            ]
        )
        nlp = _FakeNLP([doc])
        svc = self._svc(nlp)
        result = await svc.analyze_word(
            "καὶ", "grc", context="καὶ λόγος καὶ", word_occurrence=1
        )
        assert result["pos"] == "Adverb"  # second token, not the conjunction

    async def test_word_missing_from_context_falls_back_to_word_alone(self):
        context_doc = _FakeDoc([_FakeWord("μῆνιν", "μῆνις", "NOUN")])
        word_doc = _FakeDoc([_FakeWord("ξίφος", "ξίφος", "NOUN")])
        nlp = _FakeNLP([context_doc, word_doc])
        svc = self._svc(nlp)
        result = await svc.analyze_word("ξίφος", "grc", context="μῆνιν")
        assert nlp.calls == ["μῆνιν", "ξίφος"]
        assert result["lemma"] == "ξίφος"

    async def test_no_context_analyzes_word_only(self):
        word_doc = _FakeDoc([_FakeWord("ξίφος", "ξίφος", "NOUN")])
        nlp = _FakeNLP([word_doc])
        svc = self._svc(nlp)
        result = await svc.analyze_word("ξίφος", "grc")
        assert nlp.calls == ["ξίφος"]
        assert result["lemma"] == "ξίφος"

    async def test_word_alone_doc_empty_returns_fallback(self):
        nlp = _FakeNLP([_FakeDoc([]), _FakeDoc([])])
        svc = self._svc(nlp)
        result = await svc.analyze_word("ξίφος", "grc", context="μῆνιν")
        assert result["pos"] == "Unknown"
