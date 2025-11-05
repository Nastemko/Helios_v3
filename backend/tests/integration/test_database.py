"""
Integration tests for database operations.
Uses real test database (SQLite in-memory) with no mocks.
"""

import pytest
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError
from src.models.user import User
from src.models.text import Text, TextSegment
from src.models.annotation import Annotation


class TestDatabaseConnection:
    """Test database connection and setup."""
    
    def test_database_connection(self, db_session):
        """Test that database connection is established."""
        # Simple query to verify connection
        result = db_session.execute(text("SELECT 1")).scalar()
        assert result == 1
    
    def test_create_tables(self, test_engine):
        """Test that all tables are created."""
        from src.database import Base
        
        # Check that tables exist using inspect
        inspector = inspect(test_engine)
        table_names = inspector.get_table_names()
        assert "users" in table_names
        assert "texts" in table_names
        assert "text_segments" in table_names
        assert "annotations" in table_names


class TestUserCRUD:
    """Test User model CRUD operations."""
    
    def test_create_user(self, db_session):
        """Test creating a new user."""
        user = User(
            email="newuser@example.com",
            oauth_provider="google",
            oauth_id="google_123"
        )
        
        db_session.add(user)
        db_session.commit()
        
        # Verify user was created
        assert user.id is not None
        assert user.created_at is not None
    
    def test_read_user(self, db_session, test_user):
        """Test reading a user from database."""
        user = db_session.query(User).filter(User.id == test_user.id).first()
        
        assert user is not None
        assert user.email == test_user.email
        assert user.oauth_id == test_user.oauth_id
    
    def test_update_user(self, db_session, test_user):
        """Test updating user information."""
        test_user.email = "updated@example.com"
        db_session.commit()
        
        # Fetch again and verify
        user = db_session.query(User).filter(User.id == test_user.id).first()
        assert user.email == "updated@example.com"
    
    def test_delete_user(self, db_session):
        """Test deleting a user."""
        user = User(
            email="deleteme@example.com",
            oauth_provider="google",
            oauth_id="delete_123"
        )
        db_session.add(user)
        db_session.commit()
        user_id = user.id
        
        # Delete user
        db_session.delete(user)
        db_session.commit()
        
        # Verify deletion
        deleted_user = db_session.query(User).filter(User.id == user_id).first()
        assert deleted_user is None
    
    def test_user_unique_email(self, db_session, test_user):
        """Test that email must be unique."""
        duplicate_user = User(
            email=test_user.email,  # Same email
            oauth_provider="google",
            oauth_id="different_oauth_id"
        )
        
        db_session.add(duplicate_user)
        
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestTextCRUD:
    """Test Text model CRUD operations."""
    
    def test_create_text(self, db_session):
        """Test creating a new text."""
        text = Text(
            urn="urn:cts:greekLit:tlg0003.tlg001.perseus-grc1",
            title="History of the Peloponnesian War",
            author="Thucydides",
            language="grc"
        )
        
        db_session.add(text)
        db_session.commit()
        
        assert text.id is not None
    
    def test_read_text(self, db_session, sample_text):
        """Test reading a text from database."""
        text = db_session.query(Text).filter(Text.id == sample_text.id).first()
        
        assert text is not None
        assert text.urn == sample_text.urn
        assert text.title == sample_text.title
    
    def test_update_text(self, db_session, sample_text):
        """Test updating text information."""
        sample_text.title = "Updated Title"
        db_session.commit()
        
        text = db_session.query(Text).filter(Text.id == sample_text.id).first()
        assert text.title == "Updated Title"
    
    def test_text_segments_relationship(self, db_session, sample_text):
        """Test relationship between Text and TextSegments."""
        segment = TextSegment(
            text_id=sample_text.id,
            reference="1.1",
            content="Test content",
            sequence=1
        )
        db_session.add(segment)
        db_session.commit()
        
        # Fetch text with segments
        text = db_session.query(Text).filter(Text.id == sample_text.id).first()
        assert len(text.segments) > 0


class TestAnnotationCRUD:
    """Test Annotation model CRUD operations."""
    
    def test_create_annotation(self, db_session, test_user, sample_segment):
        """Test creating a new annotation."""
        annotation = Annotation(
            user_id=test_user.id,
            text_id=sample_segment.text_id,
            segment_id=sample_segment.id,
            word="test",
            note="Test note"
        )
        
        db_session.add(annotation)
        db_session.commit()
        
        assert annotation.id is not None
        assert annotation.created_at is not None
    
    def test_read_annotation(self, db_session, sample_annotation):
        """Test reading an annotation from database."""
        annotation = db_session.query(Annotation).filter(
            Annotation.id == sample_annotation.id
        ).first()
        
        assert annotation is not None
        assert annotation.word == sample_annotation.word
    
    def test_update_annotation(self, db_session, sample_annotation):
        """Test updating an annotation."""
        sample_annotation.note = "Updated note"
        db_session.commit()
        
        annotation = db_session.query(Annotation).filter(
            Annotation.id == sample_annotation.id
        ).first()
        assert annotation.note == "Updated note"
    
    def test_delete_annotation(self, db_session, sample_annotation):
        """Test deleting an annotation."""
        annotation_id = sample_annotation.id
        
        db_session.delete(sample_annotation)
        db_session.commit()
        
        deleted = db_session.query(Annotation).filter(
            Annotation.id == annotation_id
        ).first()
        assert deleted is None
    
    def test_annotations_isolated_by_user(self, db_session, test_user, sample_segment):
        """Test that users only see their own annotations."""
        # Create another user
        user2 = User(
            email="user2@example.com",
            oauth_provider="google",
            oauth_id="google_456"
        )
        db_session.add(user2)
        db_session.commit()
        
        # Create annotations for both users
        ann1 = Annotation(
            user_id=test_user.id,
            text_id=sample_segment.text_id,
            segment_id=sample_segment.id,
            word="word1",
            note="User 1 note"
        )
        ann2 = Annotation(
            user_id=user2.id,
            text_id=sample_segment.text_id,
            segment_id=sample_segment.id,
            word="word2",
            note="User 2 note"
        )
        db_session.add_all([ann1, ann2])
        db_session.commit()
        
        # Fetch annotations for user 1
        user1_annotations = db_session.query(Annotation).filter(
            Annotation.user_id == test_user.id
        ).all()
        
        # Should only see their own
        assert len(user1_annotations) >= 1
        assert all(ann.user_id == test_user.id for ann in user1_annotations)


class TestTransactions:
    """Test database transaction handling."""
    
    def test_transaction_commit(self, db_session):
        """Test successful transaction commit."""
        user = User(
            email="commit@example.com",
            oauth_provider="google",
            oauth_id="commit_123"
        )
        
        db_session.add(user)
        db_session.commit()
        
        # Verify it persisted
        found = db_session.query(User).filter(User.email == "commit@example.com").first()
        assert found is not None
    
    def test_transaction_rollback(self, db_session):
        """Test transaction rollback on error."""
        user = User(
            email="rollback@example.com",
            oauth_provider="google",
            oauth_id="rollback_123"
        )
        
        db_session.add(user)
        db_session.flush()  # Write to session but don't commit
        
        # Rollback
        db_session.rollback()
        
        # Should not be in database
        found = db_session.query(User).filter(User.email == "rollback@example.com").first()
        assert found is None

