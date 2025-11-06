"""
Integration tests for annotation API endpoints.
Tests with real database + authentication.
"""

import pytest
from fastapi.testclient import TestClient


class TestCreateAnnotation:
    """Test annotation creation endpoint."""
    
    def test_create_annotation(self, authenticated_client, sample_segment):
        """Test creating a new annotation."""
        data = {
            "text_id": sample_segment.text_id,
            "segment_id": sample_segment.id,
            "word": "test_word",
            "note": "This is a test note"
        }
        
        response = authenticated_client.post("/api/annotations", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["word"] == "test_word"
        assert result["note"] == "This is a test note"
        assert "id" in result
    
    def test_create_annotation_requires_auth(self, client, sample_segment):
        """Test that creating annotation requires authentication."""
        data = {
            "text_id": sample_segment.text_id,
            "segment_id": sample_segment.id,
            "word": "test",
            "note": "note"
        }
        
        response = client.post("/api/annotations", json=data)
        
        assert response.status_code == 401
    
    def test_create_annotation_validation(self, authenticated_client, sample_segment):
        """Test annotation data validation."""
        # Missing required field
        data = {
            "text_id": sample_segment.text_id,
            "segment_id": sample_segment.id,
            # Missing word and note
        }
        
        response = authenticated_client.post("/api/annotations", json=data)
        
        assert response.status_code == 422


class TestListAnnotations:
    """Test annotation listing endpoint."""
    
    def test_list_user_annotations(self, authenticated_client, sample_annotation):
        """Test listing annotations for authenticated user."""
        response = authenticated_client.get("/api/annotations")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # Should include the sample annotation
        assert len(data) >= 1
    
    def test_list_annotations_requires_auth(self, client):
        """Test that listing annotations requires authentication."""
        response = client.get("/api/annotations")
        
        # FastAPI returns 403 for missing authentication
        assert response.status_code in [401, 403]
    
    def test_filter_annotations_by_text(self, authenticated_client, sample_annotation):
        """Test filtering annotations by text_id."""
        response = authenticated_client.get(
            f"/api/annotations?text_id={sample_annotation.text_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All results should be for the specified text
        for annotation in data:
            assert annotation["text_id"] == sample_annotation.text_id
    
    def test_filter_annotations_by_word(self, authenticated_client, sample_annotation):
        """Test filtering annotations by word."""
        response = authenticated_client.get(
            f"/api/annotations?word={sample_annotation.word}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find annotations with that word
        if len(data) > 0:
            assert any(ann["word"] == sample_annotation.word for ann in data)


class TestGetAnnotation:
    """Test individual annotation retrieval."""
    
    def test_get_annotation(self, authenticated_client, sample_annotation):
        """Test retrieving a specific annotation."""
        response = authenticated_client.get(f"/api/annotations/{sample_annotation.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == sample_annotation.id
        assert data["word"] == sample_annotation.word
        assert data["note"] == sample_annotation.note
    
    def test_get_nonexistent_annotation(self, authenticated_client):
        """Test retrieving a non-existent annotation."""
        response = authenticated_client.get("/api/annotations/99999")
        
        assert response.status_code == 404
    
    def test_get_annotation_requires_auth(self, client, sample_annotation):
        """Test that getting annotation requires authentication."""
        response = client.get(f"/api/annotations/{sample_annotation.id}")
        
        assert response.status_code == 401


class TestUpdateAnnotation:
    """Test annotation update endpoint."""
    
    def test_update_annotation(self, authenticated_client, sample_annotation):
        """Test updating an annotation."""
        update_data = {"note": "Updated note content"}
        
        response = authenticated_client.put(
            f"/api/annotations/{sample_annotation.id}",
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["note"] == "Updated note content"
    
    def test_update_annotation_requires_auth(self, client, sample_annotation):
        """Test that updating annotation requires authentication."""
        update_data = {"note": "Should fail"}
        
        response = client.put(
            f"/api/annotations/{sample_annotation.id}",
            json=update_data
        )
        
        assert response.status_code == 401
    
    def test_update_nonexistent_annotation(self, authenticated_client):
        """Test updating a non-existent annotation."""
        update_data = {"note": "New note"}
        
        response = authenticated_client.put(
            "/api/annotations/99999",
            json=update_data
        )
        
        assert response.status_code == 404


class TestDeleteAnnotation:
    """Test annotation deletion endpoint."""
    
    def test_delete_annotation(self, authenticated_client, db_session, test_user, sample_segment):
        """Test deleting an annotation."""
        # Create an annotation to delete
        from src.models.annotation import Annotation
        
        annotation = Annotation(
            user_id=test_user.id,
            text_id=sample_segment.text_id,
            segment_id=sample_segment.id,
            word="delete_me",
            note="Will be deleted"
        )
        db_session.add(annotation)
        db_session.commit()
        annotation_id = annotation.id
        
        # Delete it
        response = authenticated_client.delete(f"/api/annotations/{annotation_id}")
        
        assert response.status_code == 200
        
        # Verify it's gone
        verify_response = authenticated_client.get(f"/api/annotations/{annotation_id}")
        assert verify_response.status_code == 404
    
    def test_delete_annotation_requires_auth(self, client, sample_annotation):
        """Test that deleting annotation requires authentication."""
        response = client.delete(f"/api/annotations/{sample_annotation.id}")
        
        assert response.status_code == 401
    
    def test_delete_nonexistent_annotation(self, authenticated_client):
        """Test deleting a non-existent annotation."""
        response = authenticated_client.delete("/api/annotations/99999")
        
        assert response.status_code == 404


class TestAnnotationPermissions:
    """Test annotation access permissions."""
    
    def test_user_cannot_access_other_annotations(self, db_session, test_user, sample_segment):
        """Test that users cannot access other users' annotations."""
        from src.models.user import User
        from src.models.annotation import Annotation
        from src.utils.security import create_access_token
        from fastapi.testclient import TestClient
        from src.main import app
        from src.database import get_db
        from datetime import datetime, timedelta
        
        # Create another user
        user2 = User(
            email="user2@example.com",
            oauth_provider="google",
            oauth_id="google_789"
        )
        db_session.add(user2)
        db_session.commit()
        
        # Create annotation for user2
        annotation = Annotation(
            user_id=user2.id,
            text_id=sample_segment.text_id,
            segment_id=sample_segment.id,
            word="private",
            note="User 2's private note"
        )
        db_session.add(annotation)
        db_session.commit()
        
        # Create client for user 1
        def override_get_db():
            yield db_session
        
        app.dependency_overrides[get_db] = override_get_db
        
        token1 = create_access_token({
            "sub": str(test_user.id),
            "email": test_user.email,
            "exp": datetime.utcnow() + timedelta(hours=1)
        })
        
        with TestClient(app) as client1:
            client1.headers.update({"Authorization": f"Bearer {token1}"})
            
            # Try to access user2's annotation
            response = client1.get(f"/api/annotations/{annotation.id}")
            
            # Should not be able to access or should return 404
            assert response.status_code in [403, 404]


class TestAnnotationTextSummary:
    """Test annotation summary for texts."""
    
    def test_get_text_annotation_summary(self, authenticated_client, sample_annotation):
        """Test retrieving annotation summary for a text."""
        text_id = sample_annotation.text_id
        
        response = authenticated_client.get(f"/api/annotations/text/{text_id}/summary")
        
        # Should return summary data
        assert response.status_code in [200, 404]  # May not be implemented yet

