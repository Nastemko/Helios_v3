"""
Unit tests for morphology service.
Tests with real CLTK library (no mocks).
"""

import pytest
from src.services.morphology import MorphologyService


@pytest.fixture(scope="module")
def morphology_service():
    """Create a morphology service instance for all tests in this module."""
    service = MorphologyService()
    return service


class TestGreekMorphology:
    """Test Greek word analysis."""
    
    def test_greek_word_analysis(self, morphology_service):
        """Test analyzing a common Greek word."""
        result = morphology_service.analyze_word("λόγος", "Greek")
        
        assert result is not None
        assert "word" in result
        assert result["word"] == "λόγος"
        assert "analyses" in result or "lemma" in result
    
    def test_greek_verb_analysis(self, morphology_service):
        """Test analyzing a Greek verb."""
        result = morphology_service.analyze_word("ἐστι", "Greek")
        
        assert result is not None
        assert result["word"] == "ἐστι"
    
    def test_greek_with_accents(self, morphology_service):
        """Test Greek words with various accents and breathing marks."""
        words = ["μῆνιν", "θεά", "Ἀχιλλεύς"]
        
        for word in words:
            result = morphology_service.analyze_word(word, "Greek")
            assert result is not None
            assert result["word"] == word
    
    def test_greek_case_sensitivity(self, morphology_service):
        """Test that Greek analysis handles capitalization."""
        # Test both capitalized and lowercase
        result1 = morphology_service.analyze_word("Ἀχιλλεύς", "Greek")
        result2 = morphology_service.analyze_word("ἀχιλλεύς", "Greek")
        
        assert result1 is not None
        assert result2 is not None


class TestLatinMorphology:
    """Test Latin word analysis."""
    
    def test_latin_word_analysis(self, morphology_service):
        """Test analyzing a common Latin word."""
        result = morphology_service.analyze_word("arma", "Latin")
        
        assert result is not None
        assert "word" in result
        assert result["word"] == "arma"
        assert "analyses" in result or "lemma" in result
    
    def test_latin_verb_analysis(self, morphology_service):
        """Test analyzing a Latin verb."""
        result = morphology_service.analyze_word("cano", "Latin")
        
        assert result is not None
        assert result["word"] == "cano"
    
    def test_latin_multiple_forms(self, morphology_service):
        """Test Latin words with multiple possible forms."""
        words = ["virum", "Troiae", "bellum"]
        
        for word in words:
            result = morphology_service.analyze_word(word, "Latin")
            assert result is not None
            assert result["word"] == word
    
    def test_latin_case_variations(self, morphology_service):
        """Test Latin words with different cases."""
        # Test nominative and genitive forms
        result1 = morphology_service.analyze_word("poeta", "Latin")
        result2 = morphology_service.analyze_word("poetae", "Latin")
        
        assert result1 is not None
        assert result2 is not None


class TestUnknownWords:
    """Test handling of unknown or invalid words."""
    
    def test_unknown_greek_word(self, morphology_service):
        """Test analyzing a nonsense Greek word."""
        result = morphology_service.analyze_word("zzzzzzz", "Greek")
        
        # Should still return a result, even if analysis is empty
        assert result is not None
        assert result["word"] == "zzzzzzz"
    
    def test_unknown_latin_word(self, morphology_service):
        """Test analyzing a nonsense Latin word."""
        result = morphology_service.analyze_word("xxxyyy", "Latin")
        
        assert result is not None
        assert result["word"] == "xxxyyy"
    
    def test_empty_word(self, morphology_service):
        """Test analyzing an empty string."""
        result = morphology_service.analyze_word("", "Greek")
        
        # Should handle gracefully
        assert result is not None
    
    def test_numeric_word(self, morphology_service):
        """Test analyzing numbers."""
        result = morphology_service.analyze_word("123", "Latin")
        
        assert result is not None
        assert result["word"] == "123"


class TestLanguageSupport:
    """Test language detection and support."""
    
    def test_unsupported_language(self, morphology_service):
        """Test handling of unsupported language."""
        with pytest.raises((ValueError, KeyError, Exception)):
            morphology_service.analyze_word("hello", "English")
    
    def test_case_insensitive_language(self, morphology_service):
        """Test that language names are handled consistently."""
        result1 = morphology_service.analyze_word("arma", "Latin")
        result2 = morphology_service.analyze_word("arma", "latin")
        
        # Both should work or both should fail consistently
        assert (result1 is not None) == (result2 is not None)


class TestContextualAnalysis:
    """Test morphology analysis with context."""
    
    def test_greek_word_with_context(self, morphology_service):
        """Test analyzing Greek word with surrounding context."""
        word = "θεά"
        context = "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος"
        
        result = morphology_service.analyze_word(word, "Greek", context=context)
        
        assert result is not None
        assert result["word"] == word
    
    def test_latin_word_with_context(self, morphology_service):
        """Test analyzing Latin word with surrounding context."""
        word = "arma"
        context = "Arma virumque cano, Troiae qui primus ab oris"
        
        result = morphology_service.analyze_word(word, "Latin", context=context)
        
        assert result is not None
        assert result["word"] == word

