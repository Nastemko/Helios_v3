import os
import unittest
from unittest.mock import patch

# To run this test, it's expected that the `src` directory is in the Python path.
# For example, by running `pytest` from the `backend` directory, or by setting PYTHONPATH.
from config import Settings


class TestConfig(unittest.TestCase):
    """Unit tests for the application configuration."""

    @patch.dict(
        os.environ,
        {
            "APP_NAME": "Test Helios API",
            "DEBUG": "True",
            "DATABASE_URL": "postgresql://test:password@db:5432/testdb",
            "SECRET_KEY": "test-secret-key-from-env",
            "ALGORITHM": "HS512",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
            "GOOGLE_CLIENT_ID": "test-google-id-from-env",
            "GOOGLE_CLIENT_SECRET": "test-google-secret-from-env",
            # pydantic_settings can parse comma-separated strings into a list
            "CORS_ORIGINS": '["http://test.com", "http://anothertest.com"]',
            "MODELS_DIR": "/test/models",
            "PERSEUS_DATA_DIR": "/test/perseus",
            "OLLAMA_BASE_URL": "http://testhost:11434",
            "OLLAMA_MODEL": "test-llama-model",
            "OLLAMA_EMBEDDING_MODEL": "test-embedding-model",
            "OLLAMA_TIMEOUT": "240",
            "LLM_ENABLED": "False",
            "POSTGRES_HOST": "test-postgres-host",
            "POSTGRES_PORT": "5439",
            "POSTGRES_DB": "test-postgres-db",
            "POSTGRES_USER": "test-postgres-user",
            "POSTGRES_PASSWORD": "test-postgres-password",
        },
    )
    def test_settings_load_from_env(self):
        """
        Test that the Settings class correctly loads values from environment variables.
        """
        # The `Settings` object is instantiated which triggers reading from the
        # environment variables patched by the decorator.
        # We need to create a new instance to test this.
        settings = Settings()

        # Assert that the settings have been loaded correctly from the mock env
        self.assertEqual(settings.APP_NAME, "Test Helios API")
        self.assertTrue(settings.DEBUG)
        self.assertEqual(
            settings.DATABASE_URL, "postgresql://test:password@db:5432/testdb"
        )
        self.assertEqual(settings.SECRET_KEY, "test-secret-key-from-env")
        self.assertEqual(settings.ALGORITHM, "HS512")
        self.assertEqual(settings.ACCESS_TOKEN_EXPIRE_MINUTES, 30)
        self.assertEqual(settings.GOOGLE_CLIENT_ID, "test-google-id-from-env")
        self.assertEqual(settings.GOOGLE_CLIENT_SECRET, "test-google-secret-from-env")
        self.assertEqual(
            settings.CORS_ORIGINS, ["http://test.com", "http://anothertest.com"]
        )
        self.assertEqual(settings.MODELS_DIR, "/test/models")
        self.assertEqual(settings.PERSEUS_DATA_DIR, "/test/perseus")
        self.assertEqual(settings.OLLAMA_BASE_URL, "http://testhost:11434")
        self.assertEqual(settings.OLLAMA_MODEL, "test-llama-model")
        self.assertEqual(settings.OLLAMA_EMBEDDING_MODEL, "test-embedding-model")
        self.assertEqual(settings.OLLAMA_TIMEOUT, 240)
        self.assertFalse(settings.LLM_ENABLED)
        self.assertEqual(settings.POSTGRES_HOST, "test-postgres-host")
        self.assertEqual(settings.POSTGRES_PORT, 5439)
        self.assertEqual(settings.POSTGRES_DB, "test-postgres-db")
        self.assertEqual(settings.POSTGRES_USER, "test-postgres-user")
        self.assertEqual(settings.POSTGRES_PASSWORD, "test-postgres-password")

    def test_default_settings(self):
        """
        Test that the Settings class uses default values when no environment variables are set.
        """
        # Use patch.dict with clear=True to ensure no existing environment variables interfere
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # Assert that the default values are used
            self.assertEqual(settings.APP_NAME, "Helios API")
            self.assertFalse(settings.DEBUG)
            self.assertEqual(settings.DATABASE_URL, "sqlite:///./helios_local.db")
            self.assertEqual(settings.SECRET_KEY, "dev-secret-key-change-in-production")
            self.assertEqual(settings.ALGORITHM, "HS256")
            self.assertEqual(settings.ACCESS_TOKEN_EXPIRE_MINUTES, 60 * 24 * 7)
            self.assertEqual(settings.GOOGLE_CLIENT_ID, "")
            self.assertEqual(settings.GOOGLE_CLIENT_SECRET, "")

            self.assertEqual(
                settings.CORS_ORIGINS,
                ["http://localhost:3000", "http://localhost:5173"],
            )
            self.assertEqual(settings.MODELS_DIR, "./models")
            self.assertEqual(settings.PERSEUS_DATA_DIR, "../canonical-greekLit/data")
            self.assertEqual(settings.OLLAMA_BASE_URL, "http://localhost:11434")
            self.assertEqual(settings.OLLAMA_MODEL, "llama3.2:8b")
            self.assertEqual(settings.OLLAMA_EMBEDDING_MODEL, "nomic-embed-text")
            self.assertEqual(settings.OLLAMA_TIMEOUT, 120)
            self.assertTrue(settings.LLM_ENABLED)
            self.assertEqual(settings.POSTGRES_HOST, "localhost")
            self.assertEqual(settings.POSTGRES_PORT, 5432)
            self.assertEqual(settings.POSTGRES_DB, "helios")
            self.assertEqual(settings.POSTGRES_USER, "heliosuser")
            self.assertEqual(settings.POSTGRES_PASSWORD, "")


if __name__ == "__main__":
    unittest.main()
