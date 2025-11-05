"""
Unit tests for configuration management.
Tests config loading and environment variable handling.
"""

import pytest
import os
from src.config import Settings


class TestConfigDefaults:
    """Test default configuration values."""
    
    def test_default_config_values(self):
        """Test that configuration has sensible defaults."""
        settings = Settings()
        
        # Database should have a default
        assert settings.DATABASE_URL is not None
        
        # Secret key should exist
        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0
        
        # Token expiry should be positive
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0
        
        # CORS origins should be a list
        assert isinstance(settings.CORS_ORIGINS, list)
    
    def test_database_url_construction(self):
        """Test database URL format."""
        settings = Settings()
        
        # Should be a valid connection string
        assert "://" in settings.DATABASE_URL
        
        # Should start with a valid database type
        assert (
            settings.DATABASE_URL.startswith("postgresql://") or
            settings.DATABASE_URL.startswith("sqlite://")
        )
    
    def test_models_directory_path(self):
        """Test models directory configuration."""
        settings = Settings()
        
        assert settings.MODELS_DIR is not None
        assert isinstance(settings.MODELS_DIR, str)
    
    def test_perseus_data_directory(self):
        """Test Perseus data directory configuration."""
        settings = Settings()
        
        assert settings.PERSEUS_DATA_DIR is not None
        assert isinstance(settings.PERSEUS_DATA_DIR, str)


class TestEnvironmentVariables:
    """Test environment variable override."""
    
    def test_environment_variable_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        # Set environment variable
        monkeypatch.setenv("SECRET_KEY", "test_secret_key_12345")
        
        settings = Settings()
        
        assert settings.SECRET_KEY == "test_secret_key_12345"
    
    def test_database_url_override(self, monkeypatch):
        """Test overriding database URL via environment."""
        test_db_url = "postgresql://testuser:testpass@localhost/testdb"
        monkeypatch.setenv("DATABASE_URL", test_db_url)
        
        settings = Settings()
        
        assert settings.DATABASE_URL == test_db_url
    
    def test_cors_origins_override(self, monkeypatch):
        """Test overriding CORS origins via environment."""
        # Pydantic expects JSON array format for list fields
        test_origins = '["http://localhost:3000","http://localhost:5173","https://example.com"]'
        monkeypatch.setenv("CORS_ORIGINS", test_origins)
        
        settings = Settings()
        
        # Should be parsed into a list
        assert isinstance(settings.CORS_ORIGINS, list)
        assert len(settings.CORS_ORIGINS) == 3
        assert "http://localhost:3000" in settings.CORS_ORIGINS
        assert "https://example.com" in settings.CORS_ORIGINS
    
    def test_debug_mode_toggle(self, monkeypatch):
        """Test toggling debug mode."""
        monkeypatch.setenv("DEBUG", "True")
        settings1 = Settings()
        assert settings1.DEBUG is True
        
        monkeypatch.setenv("DEBUG", "False")
        settings2 = Settings()
        assert settings2.DEBUG is False
    
    def test_ollama_configuration(self, monkeypatch):
        """Test Ollama service configuration."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "custom-model")
        
        settings = Settings()
        
        assert settings.OLLAMA_BASE_URL == "http://custom:11434"
        assert settings.OLLAMA_MODEL == "custom-model"


class TestConfigValidation:
    """Test configuration validation."""
    
    def test_secret_key_minimum_length(self):
        """Test that secret key has minimum length for security."""
        settings = Settings()
        
        # Secret key should be at least 32 characters for security
        assert len(settings.SECRET_KEY) >= 32
    
    def test_token_expiry_reasonable(self):
        """Test that token expiry is within reasonable bounds."""
        settings = Settings()
        
        # Token expiry should be between 5 minutes and 30 days
        assert 5 <= settings.ACCESS_TOKEN_EXPIRE_MINUTES <= 43200  # 30 days
    
    def test_cors_origins_format(self):
        """Test that CORS origins are properly formatted."""
        settings = Settings()
        
        for origin in settings.CORS_ORIGINS:
            # Each origin should be a valid URL or wildcard
            assert origin == "*" or origin.startswith("http://") or origin.startswith("https://")

