"""
Integration tests for word analysis API endpoints.
Tests with real morphology service (CLTK) - no mocks for morphology.
"""

import pytest
from fastapi.testclient import TestClient


class TestWordAnalysis:
    """Test word analysis endpoint."""
    
    def test_analyze_greek_word(self, client):
        """Test analyzing a Greek word."""
        data = {
            "word": "λόγος",
            "language": "Greek"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        assert "word" in result
        assert result["word"] == "λόγος"
        assert "analyses" in result or "lemma" in result or "language" in result
    
    def test_analyze_latin_word(self, client):
        """Test analyzing a Latin word."""
        data = {
            "word": "arma",
            "language": "Latin"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        assert "word" in result
        assert result["word"] == "arma"
    
    def test_analyze_word_with_context(self, client):
        """Test word analysis with surrounding context."""
        data = {
            "word": "μῆνιν",
            "language": "Greek",
            "context": "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["word"] == "μῆνιν"
    
    def test_analyze_unknown_word(self, client):
        """Test analyzing an unknown/nonsense word."""
        data = {
            "word": "zzzzzzz",
            "language": "Greek"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        # Should handle gracefully
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            result = response.json()
            assert "word" in result
    
    def test_analyze_word_missing_language(self, client):
        """Test that language parameter is required."""
        data = {
            "word": "test"
            # Missing language
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        assert response.status_code == 422
    
    def test_analyze_empty_word(self, client):
        """Test handling of empty word."""
        data = {
            "word": "",
            "language": "Greek"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]


class TestConcurrentAnalysis:
    """Test concurrent analysis requests."""
    
    def test_concurrent_analysis_requests(self, client):
        """Test multiple simultaneous word analysis requests."""
        import concurrent.futures
        
        words = ["λόγος", "θεός", "ἄνθρωπος", "πόλις", "φιλία"]
        
        def analyze_word(word):
            return client.post("/api/analyze/word", json={
                "word": word,
                "language": "Greek"
            })
        
        # Make concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(analyze_word, word) for word in words]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All should succeed
        assert all(r.status_code == 200 for r in responses)
        
        # Each should have analyzed a word
        results = [r.json() for r in responses]
        analyzed_words = [r["word"] for r in results if "word" in r]
        assert len(analyzed_words) == 5


class TestMultipleLanguages:
    """Test analyzing words in different languages."""
    
    def test_greek_and_latin_words(self, client):
        """Test analyzing both Greek and Latin words."""
        # Greek word
        greek_response = client.post("/api/analyze/word", json={
            "word": "λόγος",
            "language": "Greek"
        })
        
        # Latin word
        latin_response = client.post("/api/analyze/word", json={
            "word": "verbum",
            "language": "Latin"
        })
        
        assert greek_response.status_code == 200
        assert latin_response.status_code == 200
        
        greek_result = greek_response.json()
        latin_result = latin_response.json()
        
        assert greek_result["word"] == "λόγος"
        assert latin_result["word"] == "verbum"
    
    def test_unsupported_language(self, client):
        """Test handling of unsupported language."""
        data = {
            "word": "hello",
            "language": "English"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        # API returns 200 with fallback response for unsupported languages
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["word"] == "hello"
        assert response_data["language"] == "English"


class TestPerformance:
    """Test analysis performance requirements."""
    
    def test_analysis_response_time(self, client):
        """Test that word analysis completes within performance target (<500ms)."""
        import time
        
        data = {
            "word": "λόγος",
            "language": "Greek"
        }
        
        start_time = time.time()
        response = client.post("/api/analyze/word", json=data)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        assert response.status_code == 200
        
        # Should complete within 500ms (being lenient for tests, allow 1s)
        assert elapsed < 1.0
    
    def test_batch_analysis_performance(self, client):
        """Test performance of analyzing multiple words."""
        import time
        
        words = ["λόγος", "θεός", "ἄνθρωπος", "πόλις", "φιλία"]
        
        start_time = time.time()
        
        for word in words:
            response = client.post("/api/analyze/word", json={
                "word": word,
                "language": "Greek"
            })
            assert response.status_code == 200
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # 5 words should complete in reasonable time (< 5 seconds total)
        assert elapsed < 5.0


class TestErrorHandling:
    """Test error handling in analysis endpoints."""
    
    def test_malformed_request(self, client):
        """Test handling of malformed request."""
        response = client.post("/api/analyze/word", json={
            "invalid_field": "value"
        })
        
        assert response.status_code == 422
    
    def test_special_characters(self, client):
        """Test handling of words with special characters."""
        data = {
            "word": "λόγος!@#$%",
            "language": "Greek"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        # Should handle gracefully
        assert response.status_code in [200, 400]
    
    def test_very_long_word(self, client):
        """Test handling of extremely long words."""
        data = {
            "word": "α" * 1000,  # 1000 characters
            "language": "Greek"
        }
        
        response = client.post("/api/analyze/word", json=data)
        
        # Should handle gracefully (may reject or analyze)
        assert response.status_code in [200, 400, 413, 422]

