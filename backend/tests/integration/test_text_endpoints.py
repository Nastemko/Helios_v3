"""
Integration tests for text API endpoints.
Tests with real database + FastAPI TestClient (no mocks for internal services).
"""

import pytest
from fastapi.testclient import TestClient


class TestListTexts:
    """Test text listing endpoint."""
    
    def test_list_texts_endpoint(self, client, multiple_texts):
        """Test listing all texts."""
        response = client.get("/api/texts")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= 3  # We created 3 texts
    
    def test_list_texts_pagination(self, client, multiple_texts):
        """Test pagination parameters."""
        response = client.get("/api/texts?skip=0&limit=2")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) <= 2
    
    def test_search_texts(self, client, multiple_texts):
        """Test text search functionality."""
        response = client.get("/api/texts?search=Homer")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find Homer's works
        assert any("Homer" in text["author"] for text in data)
    
    def test_filter_by_author(self, client, multiple_texts):
        """Test filtering texts by author."""
        response = client.get("/api/texts?author=Homer")
        
        assert response.status_code == 200
        data = response.json()
        
        # All results should be by Homer
        for text in data:
            assert text["author"] == "Homer"
    
    def test_filter_by_language(self, client, multiple_texts):
        """Test filtering texts by language."""
        response = client.get("/api/texts?language=Greek")
        
        assert response.status_code == 200
        data = response.json()
        
        # All results should be Greek
        for text in data:
            assert text["language"] == "Greek"


class TestGetText:
    """Test individual text retrieval."""
    
    def test_get_text_by_urn(self, client, sample_text):
        """Test retrieving a specific text by URN."""
        urn = sample_text.urn
        response = client.get(f"/api/texts/{urn}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["urn"] == urn
        assert data["title"] == sample_text.title
        assert data["author"] == sample_text.author
    
    def test_get_nonexistent_text(self, client):
        """Test retrieving a non-existent text."""
        response = client.get("/api/texts/urn:cts:nonexistent:text")
        
        assert response.status_code == 404
    
    def test_get_text_with_pagination(self, client, sample_text):
        """Test text retrieval with segment pagination."""
        urn = sample_text.urn
        response = client.get(f"/api/texts/{urn}?skip=0&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have segments if they exist
        if "segments" in data:
            assert len(data["segments"]) <= 10


class TestGetSegment:
    """Test text segment retrieval."""
    
    def test_get_text_segment(self, client, sample_segment):
        """Test retrieving a specific text segment."""
        urn = sample_segment.text.urn
        reference = sample_segment.reference
        
        response = client.get(f"/api/texts/{urn}/segment/{reference}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["reference"] == reference
        assert data["content"] == sample_segment.content
    
    def test_get_nonexistent_segment(self, client, sample_text):
        """Test retrieving a non-existent segment."""
        urn = sample_text.urn
        response = client.get(f"/api/texts/{urn}/segment/99.99.99")
        
        assert response.status_code == 404


class TestTextStats:
    """Test text statistics endpoints."""
    
    def test_get_text_stats(self, client, multiple_texts):
        """Test retrieving text statistics."""
        response = client.get("/api/texts/stats/summary")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have statistics
        assert "total_texts" in data or "count" in data or len(data) > 0
    
    def test_get_authors_list(self, client, multiple_texts):
        """Test retrieving list of authors."""
        response = client.get("/api/texts/authors/list")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # Should find our test authors
        authors = [item["author"] for item in data if "author" in item]
        assert "Homer" in authors or "Vergil" in authors


class TestConcurrentRequests:
    """Test handling of concurrent requests."""
    
    def test_concurrent_text_requests(self, client, multiple_texts):
        """Test multiple simultaneous text list requests."""
        import concurrent.futures
        
        def fetch_texts():
            return client.get("/api/texts")
        
        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_texts) for _ in range(5)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All should succeed
        assert all(r.status_code == 200 for r in responses)
        
        # All should return same data
        data_sets = [r.json() for r in responses]
        assert all(len(d) == len(data_sets[0]) for d in data_sets)


class TestErrorHandling:
    """Test error handling in text endpoints."""
    
    def test_invalid_urn_format(self, client):
        """Test handling of invalid URN format."""
        response = client.get("/api/texts/invalid-urn-format")
        
        # Should handle gracefully (404 or 400)
        assert response.status_code in [400, 404]
    
    def test_invalid_pagination_params(self, client):
        """Test handling of invalid pagination parameters."""
        response = client.get("/api/texts?skip=-1&limit=0")
        
        # Should either reject or handle gracefully
        assert response.status_code in [200, 400, 422]
    
    def test_sql_injection_attempt(self, client):
        """Test protection against SQL injection."""
        malicious_input = "'; DROP TABLE texts; --"
        response = client.get(f"/api/texts?search={malicious_input}")
        
        # Should handle safely
        assert response.status_code in [200, 400]
        
        # Database should still work after
        response2 = client.get("/api/texts")
        assert response2.status_code == 200

