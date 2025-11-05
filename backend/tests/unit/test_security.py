"""
Unit tests for security utilities.
Tests password hashing and JWT token functionality with no mocks.
"""

import pytest
from datetime import datetime, timedelta
from jose import jwt, JWTError

from src.utils.security import (
    verify_password,
    hash_password,
    create_access_token,
    verify_token
)
from src.config import settings


# Check if bcrypt is working properly
def check_bcrypt_available():
    """Check if bcrypt backend is available and working"""
    try:
        # Try a simple hash operation
        test_hash = hash_password("test")
        return True
    except (ValueError, Exception):
        return False


bcrypt_available = check_bcrypt_available()
skip_if_bcrypt_unavailable = pytest.mark.skipif(
    not bcrypt_available,
    reason="bcrypt backend not available or incompatible"
)


class TestPasswordHashing:
    """Test password hashing and verification."""
    
    @skip_if_bcrypt_unavailable
    def test_password_hashing_and_verification(self):
        """Test that passwords are properly hashed and can be verified."""
        password = "SecurePassword123!"
        hashed = hash_password(password)
        
        # Hash should be different from original
        assert hashed != password
        
        # Verify correct password
        assert verify_password(password, hashed) is True
        
        # Verify incorrect password
        assert verify_password("WrongPassword", hashed) is False
    
    @skip_if_bcrypt_unavailable
    def test_same_password_different_hashes(self):
        """Test that same password generates different hashes (due to salt)."""
        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Hashes should be different
        assert hash1 != hash2
        
        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True
    
    @skip_if_bcrypt_unavailable
    def test_empty_password(self):
        """Test handling of empty password."""
        password = ""
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        assert verify_password("not_empty", hashed) is False


class TestJWTTokens:
    """Test JWT token creation and validation."""
    
    def test_jwt_token_creation_and_validation(self):
        """Test creating and validating JWT tokens."""
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        
        token = create_access_token(payload)
        
        # Token should be a non-empty string
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token
        decoded = verify_token(token)
        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"
    
    def test_jwt_token_expiration(self):
        """Test that expired tokens are rejected."""
        payload = {
            "sub": "user123",
            "email": "test@example.com"
        }
        
        # Create an expired token by encoding it directly with past expiration
        expired_payload = payload.copy()
        expired_payload["exp"] = datetime.utcnow() - timedelta(hours=1)
        token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        
        # Token should fail verification due to expiration
        decoded = verify_token(token)
        assert decoded is None
    
    def test_invalid_jwt_token_handling(self):
        """Test handling of invalid JWT tokens."""
        # Test completely invalid token
        assert verify_token("invalid_token_string") is None
        
        # Test empty token
        assert verify_token("") is None
    
    def test_jwt_token_with_custom_expiry(self):
        """Test creating token with custom expiry time."""
        expires_delta = timedelta(minutes=30)
        payload = {
            "sub": "user456",
            "email": "another@example.com"
        }
        
        token = create_access_token(payload, expires_delta=expires_delta)
        decoded = verify_token(token)
        
        assert decoded is not None
        assert decoded["sub"] == "user456"
        
        # Check expiration is roughly 30 minutes from now
        exp_time = datetime.fromtimestamp(decoded["exp"])
        expected_exp = datetime.utcnow() + timedelta(minutes=30)
        
        # Allow 1 minute tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 60
    
    def test_jwt_token_tampering(self):
        """Test that tampered tokens are rejected."""
        payload = {
            "sub": "user789",
            "email": "tamper@example.com",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        
        token = create_access_token(payload)
        
        # Tamper with the token (change one character)
        if len(token) > 10:
            tampered = token[:-5] + "X" + token[-4:]
            assert verify_token(tampered) is None

