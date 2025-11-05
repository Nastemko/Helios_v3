"""
Test configuration and fixtures for Helios backend tests.

This module provides pytest fixtures for testing with minimal mocking.
Uses real database (SQLite in-memory) and real services where possible.
Only mocks external APIs (Google OAuth, etc.).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
from typing import Generator
import os
from datetime import datetime, timedelta

# Import from src
from src.database import Base, get_db
from src.main import app
from src.models.user import User
from src.models.text import Text, TextSegment
from src.models.annotation import Annotation
from src.utils.security import create_access_token


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine (SQLite in-memory)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> TestClient:
    """Create a FastAPI test client with test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user in the database."""
    user = User(
        email="test@example.com",
        google_id="test_google_id_123",
        name="Test User",
        picture="https://example.com/picture.jpg",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Create a valid JWT token for the test user."""
    token_data = {
        "sub": str(test_user.id),
        "email": test_user.email,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return create_access_token(token_data)


@pytest.fixture
def authenticated_client(client: TestClient, auth_token: str) -> TestClient:
    """Create a test client with authentication headers."""
    client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return client


@pytest.fixture
def sample_text(db_session: Session) -> Text:
    """Create a sample text for testing."""
    text = Text(
        urn="urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
        title="Iliad",
        author="Homer",
        language="Greek",
        description="The Iliad by Homer",
        word_count=150000,
        is_public=True
    )
    db_session.add(text)
    db_session.commit()
    db_session.refresh(text)
    return text


@pytest.fixture
def sample_segment(db_session: Session, sample_text: Text) -> TextSegment:
    """Create a sample text segment for testing."""
    segment = TextSegment(
        text_id=sample_text.id,
        reference="1.1",
        content="μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        sequence_number=1
    )
    db_session.add(segment)
    db_session.commit()
    db_session.refresh(segment)
    return segment


@pytest.fixture
def sample_annotation(db_session: Session, test_user: User, sample_segment: TextSegment) -> Annotation:
    """Create a sample annotation for testing."""
    annotation = Annotation(
        user_id=test_user.id,
        text_id=sample_segment.text_id,
        segment_id=sample_segment.id,
        word="μῆνιν",
        note="The wrath of Achilles - opening word of the Iliad"
    )
    db_session.add(annotation)
    db_session.commit()
    db_session.refresh(annotation)
    return annotation


@pytest.fixture
def multiple_texts(db_session: Session) -> list[Text]:
    """Create multiple texts for testing list/search functionality."""
    texts = [
        Text(
            urn="urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
            title="Iliad",
            author="Homer",
            language="Greek",
            word_count=150000,
            is_public=True
        ),
        Text(
            urn="urn:cts:greekLit:tlg0012.tlg002.perseus-grc2",
            title="Odyssey",
            author="Homer",
            language="Greek",
            word_count=120000,
            is_public=True
        ),
        Text(
            urn="urn:cts:latinLit:phi0690.phi003.perseus-lat2",
            title="Aeneid",
            author="Vergil",
            language="Latin",
            word_count=100000,
            is_public=True
        ),
    ]
    for text in texts:
        db_session.add(text)
    db_session.commit()
    for text in texts:
        db_session.refresh(text)
    return texts


@pytest.fixture
def sample_greek_words() -> list[str]:
    """Sample Greek words for morphology testing."""
    return ["μῆνιν", "θεά", "Ἀχιλλεύς", "λόγος", "ἄνθρωπος"]


@pytest.fixture
def sample_latin_words() -> list[str]:
    """Sample Latin words for morphology testing."""
    return ["arma", "virum", "cano", "Troiae", "bellum"]


@pytest.fixture
def mock_google_oauth_response():
    """Mock response from Google OAuth."""
    return {
        "access_token": "mock_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid email profile",
        "id_token": "mock_id_token"
    }


@pytest.fixture
def mock_google_userinfo():
    """Mock user info from Google."""
    return {
        "id": "google_user_123",
        "email": "testuser@example.com",
        "verified_email": True,
        "name": "Test User",
        "given_name": "Test",
        "family_name": "User",
        "picture": "https://example.com/photo.jpg"
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")

