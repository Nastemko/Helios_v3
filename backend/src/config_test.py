import os
import unittest
from unittest.mock import patch

# To run this test, it's expected that the `src` directory is in the Python path.
# For example, by running `pytest` from the `backend` directory, or by setting PYTHONPATH.
from .config import Settings


class TestConfig(unittest.TestCase):
    """Unit tests for the application configuration."""

    @patch.dict(
        os.environ,
        {
            "APP_NAME": "Test Helios API",
            "DEBUG": "True",
            "SECRET_KEY": "test-secret-key-from-env",
            "ALGORITHM": "HS512",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
            "GOOGLE_CLIENT_ID": "test-google-id-from-env",
            "GOOGLE_CLIENT_SECRET": "test-google-secret-from-env",
            # pydantic_settings can parse comma-separated strings into a list
            "CORS_ORIGINS": '["http://test.com", "http://anothertest.com"]',
            "INSCRIPTIONS_DIR": "/test/models",
            "PERSEUS_DATA_DIR": "/test/perseus",
            "LLM_BASE_URL": "http://testhost:11434",
            "LLM_MODEL": "test-llama-model",
            "LLM_TIMEOUT": "240",
            "LLM_ENABLED": "False",
            "DATABASE_HOST": "test-postgres-host",
            "DATABASE_PORT": "5439",
            "DATABASE_DB": "test-postgres-db",
            "DATABASE_USER": "test-postgres-user",
            "DATABASE_PASSWORD": "test-postgres-password",
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
        self.assertEqual(settings.misc.APP_NAME, "Test Helios API")
        self.assertTrue(settings.misc.DEBUG)
        self.assertEqual(settings.auth.SECRET_KEY, "test-secret-key-from-env")
        self.assertEqual(settings.auth.ALGORITHM, "HS512")
        self.assertEqual(settings.auth.ACCESS_TOKEN_EXPIRE_MINUTES, 30)
        self.assertEqual(settings.auth.GOOGLE_CLIENT_ID, "test-google-id-from-env")
        self.assertEqual(
            settings.auth.GOOGLE_CLIENT_SECRET, "test-google-secret-from-env"
        )
        self.assertEqual(
            settings.misc.CORS_ORIGINS, ["http://test.com", "http://anothertest.com"]
        )
        self.assertEqual(settings.assets.INSCRIPTIONS_DIR, "/test/models")
        self.assertEqual(settings.assets.PERSEUS_DATA_DIR, "/test/perseus")
        self.assertEqual(settings.llm.BASE_URL, "http://testhost:11434")
        self.assertEqual(settings.llm.MODEL, "test-llama-model")
        self.assertEqual(settings.llm.TIMEOUT, 240)
        self.assertFalse(settings.llm.ENABLED)
        self.assertEqual(settings.database.HOST, "test-postgres-host")
        self.assertEqual(settings.database.PORT, 5439)
        self.assertEqual(settings.database.DB, "test-postgres-db")
        self.assertEqual(settings.database.USER, "test-postgres-user")
        self.assertEqual(settings.database.PASSWORD, "test-postgres-password")

    def test_default_settings(self):
        """
        Test that the Settings class uses default values when no environment variables are set.
        """
        # Use patch.dict with clear=True to ensure no existing environment variables interfere
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # Assert that the default values are used
            self.assertEqual(settings.misc.APP_NAME, "Helios API")
            self.assertFalse(settings.misc.DEBUG)
            self.assertEqual(settings.auth.SECRET_KEY, "")
            self.assertEqual(settings.auth.ALGORITHM, "HS256")
            self.assertEqual(settings.auth.ACCESS_TOKEN_EXPIRE_MINUTES, 60 * 24)
            self.assertEqual(settings.auth.GOOGLE_CLIENT_ID, "")
            self.assertEqual(settings.auth.GOOGLE_CLIENT_SECRET, "")

            self.assertEqual(
                settings.misc.CORS_ORIGINS,
                [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ],
            )
            self.assertEqual(
                settings.assets.INSCRIPTIONS_DIR, "/app/assets/inscriptions"
            )
            self.assertEqual(
                settings.assets.PERSEUS_DATA_DIR, "/app/assets/canonical-greekLit/data"
            )
            self.assertEqual(settings.llm.BASE_URL, "http://localhost:11434")
            self.assertEqual(settings.llm.MODEL, "llama3.2:3b")
            self.assertEqual(settings.llm.TIMEOUT, 120)
            self.assertTrue(settings.llm.ENABLED)
            self.assertEqual(settings.database.HOST, "localhost")
            self.assertEqual(settings.database.PORT, 5432)
            self.assertEqual(settings.database.DB, "helios")
            self.assertEqual(settings.database.USER, "heliosuser")
            self.assertEqual(settings.database.PASSWORD, "")
