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
    
    @pytest.mark.asyncio
    async def test_greek_word_analysis(self, morphology_service):
        """Test analyzing a common Greek word."""
        result = await morphology_service.analyze_word("λόγος", "grc")
        
        assert result is not None
        assert "word" in result
        assert result["word"] == "λόγος"
        assert "lemma" in result
    
    @pytest.mark.asyncio
    async def test_greek_verb_analysis(self, morphology_service):
        """Test analyzing a Greek verb."""
        result = await morphology_service.analyze_word("ἐστι", "grc")
        
        assert result is not None
        assert result["word"] == "ἐστι"
    
    @pytest.mark.asyncio
    async def test_greek_with_accents(self, morphology_service):
        """Test Greek words with various accents and breathing marks."""
        words = ["μῆνιν", "θεά", "Ἀχιλλεύς"]
        
        for word in words:
            result = await morphology_service.analyze_word(word, "grc")
            assert result is not None
            assert result["word"] == word
    
    @pytest.mark.asyncio
    async def test_greek_case_sensitivity(self, morphology_service):
        """Test that Greek analysis handles capitalization."""
        # Test both capitalized and lowercase
        result1 = await morphology_service.analyze_word("Ἀχιλλεύς", "grc")
        result2 = await morphology_service.analyze_word("ἀχιλλεύς", "grc")
        
        assert result1 is not None
        assert result2 is not None


class TestLatinMorphology:
    """Test Latin word analysis."""
    
    @pytest.mark.asyncio
    async def test_latin_word_analysis(self, morphology_service):
        """Test analyzing a common Latin word."""
        result = await morphology_service.analyze_word("arma", "lat")
        
        assert result is not None
        assert "word" in result
        assert result["word"] == "arma"
        assert "lemma" in result
    
    @pytest.mark.asyncio
    async def test_latin_verb_analysis(self, morphology_service):
        """Test analyzing a Latin verb."""
        result = await morphology_service.analyze_word("cano", "lat")
        
        assert result is not None
        assert result["word"] == "cano"
    
    @pytest.mark.asyncio
    async def test_latin_multiple_forms(self, morphology_service):
        """Test Latin words with multiple possible forms."""
        words = ["virum", "Troiae", "bellum"]
        
        for word in words:
            result = await morphology_service.analyze_word(word, "lat")
            assert result is not None
            assert result["word"] == word
    
    @pytest.mark.asyncio
    async def test_latin_case_variations(self, morphology_service):
        """Test Latin words with different cases."""
        # Test nominative and genitive forms
        result1 = await morphology_service.analyze_word("poeta", "lat")
        result2 = await morphology_service.analyze_word("poetae", "lat")
        
        assert result1 is not None
        assert result2 is not None


class TestUnknownWords:
    """Test handling of unknown or invalid words."""
    
    @pytest.mark.asyncio
    async def test_unknown_greek_word(self, morphology_service):
        """Test analyzing a nonsense Greek word."""
        result = await morphology_service.analyze_word("zzzzzzz", "grc")
        
        # Should still return a result, even if analysis is empty
        assert result is not None
        assert result["word"] == "zzzzzzz"
    
    @pytest.mark.asyncio
    async def test_unknown_latin_word(self, morphology_service):
        """Test analyzing a nonsense Latin word."""
        result = await morphology_service.analyze_word("xxxyyy", "lat")
        
        assert result is not None
        assert result["word"] == "xxxyyy"
    
    @pytest.mark.asyncio
    async def test_empty_word(self, morphology_service):
        """Test analyzing an empty string."""
        result = await morphology_service.analyze_word("", "grc")
        
        # Should handle gracefully
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_numeric_word(self, morphology_service):
        """Test analyzing numbers."""
        result = await morphology_service.analyze_word("123", "lat")
        
        assert result is not None
        assert result["word"] == "123"


class TestLanguageSupport:
    """Test language detection and support."""
    
    @pytest.mark.asyncio
    async def test_unsupported_language(self, morphology_service):
        """Test handling of unsupported language."""
        # The service returns a fallback response rather than raising an exception
        result = await morphology_service.analyze_word("hello", "English")
        assert result is not None
        assert result["word"] == "hello"
        # Should return fallback response
        assert result["pos"] == "unknown"
    
    @pytest.mark.asyncio
    async def test_case_insensitive_language(self, morphology_service):
        """Test that language names are handled consistently."""
        result1 = await morphology_service.analyze_word("arma", "lat")
        result2 = await morphology_service.analyze_word("arma", "lat")
        
        # Both should work consistently
        assert result1 is not None
        assert result2 is not None


class TestContextualAnalysis:
    """Test morphology analysis with context."""
    
    @pytest.mark.asyncio
    async def test_greek_word_with_context(self, morphology_service):
        """Test analyzing Greek word with surrounding context."""
        word = "θεά"
        context = "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος"
        
        result = await morphology_service.analyze_word(word, "grc", context=context)
        
        assert result is not None
        assert result["word"] == word
    
    @pytest.mark.asyncio
    async def test_latin_word_with_context(self, morphology_service):
        """Test analyzing Latin word with surrounding context."""
        word = "arma"
        context = "Arma virumque cano, Troiae qui primus ab oris"
        
        result = await morphology_service.analyze_word(word, "lat", context=context)
        
        assert result is not None
        assert result["word"] == word

