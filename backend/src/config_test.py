import os
import unittest
from unittest.mock import patch

# To run this test, it's expected that the `src` directory is in the Python path.
# For example, by running `pytest` from the `backend` directory, or by setting PYTHONPATH.
from .config import IthacaShardSettings, Settings


class TestConfig(unittest.TestCase):
    """Unit tests for the application configuration."""

    @patch.dict(
        os.environ,
        {
            "APP_NAME": "Test Helios API",
            "DEBUG": "True",
            "SECRET_KEY": "test-secret-key-from-env",
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


class TestValidateProduction(unittest.TestCase):
    """Tests for the production-readiness check run at startup.

    When DEBUG is off, Google OAuth is the only way to authenticate, so a boot
    without the signing key or Google credentials would leave nobody able to
    log in. That must fail loudly instead of silently.
    """

    def _settings(self, **overrides: str) -> Settings:
        """Build Settings from a clean environment plus explicit overrides.

        clear=True keeps the repository's own .env from leaking real values in.
        """
        env = {
            "DEBUG": "False",
            "SECRET_KEY": "",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
        }
        env.update(overrides)
        with patch.dict(os.environ, env, clear=True):
            return Settings()

    def test_debug_mode_skips_all_checks(self):
        """DEBUG=True: auth is disabled, so no credentials are required."""
        settings = self._settings(DEBUG="True")
        settings.validate_production()  # must not raise

    def test_production_with_all_credentials_passes(self):
        """DEBUG=False with the full set of secrets is valid."""
        settings = self._settings(
            SECRET_KEY="a-real-secret",
            GOOGLE_CLIENT_ID="a-client-id",
            GOOGLE_CLIENT_SECRET="a-client-secret",
        )
        settings.validate_production()  # must not raise

    def test_production_without_secret_key_raises(self):
        settings = self._settings(
            GOOGLE_CLIENT_ID="a-client-id",
            GOOGLE_CLIENT_SECRET="a-client-secret",
        )
        with self.assertRaises(ValueError) as ctx:
            settings.validate_production()
        self.assertIn("SECRET_KEY", str(ctx.exception))

    def test_production_without_google_client_id_raises(self):
        settings = self._settings(
            SECRET_KEY="a-real-secret",
            GOOGLE_CLIENT_SECRET="a-client-secret",
        )
        with self.assertRaises(ValueError) as ctx:
            settings.validate_production()
        self.assertIn("GOOGLE_CLIENT_ID", str(ctx.exception))

    def test_production_without_google_client_secret_raises(self):
        settings = self._settings(
            SECRET_KEY="a-real-secret",
            GOOGLE_CLIENT_ID="a-client-id",
        )
        with self.assertRaises(ValueError) as ctx:
            settings.validate_production()
        self.assertIn("GOOGLE_CLIENT_SECRET", str(ctx.exception))

    def test_error_names_every_missing_key_at_once(self):
        """All three are reported together rather than one boot at a time."""
        settings = self._settings()
        with self.assertRaises(ValueError) as ctx:
            settings.validate_production()

        message = str(ctx.exception)
        self.assertIn("SECRET_KEY", message)
        self.assertIn("GOOGLE_CLIENT_ID", message)
        self.assertIn("GOOGLE_CLIENT_SECRET", message)


class TestIthacaShardChunking(unittest.TestCase):
    """Per-machine chunking configuration."""

    def test_local_chunks_defaults_to_autodetect(self):
        """0 means 'work it out from this machine', not 'disabled'."""
        self.assertEqual(IthacaShardSettings().LOCAL_CHUNKS, 0)

    def test_min_rows_per_chunk_default(self):
        self.assertEqual(IthacaShardSettings().MIN_ROWS_PER_CHUNK, 4)

    @patch.dict(os.environ, {"ITHACA_SHARD_LOCAL_CHUNKS": "5"})
    def test_local_chunks_env_override(self):
        """Nodes differ in shape, so an explicit value must always win."""
        self.assertEqual(IthacaShardSettings().LOCAL_CHUNKS, 5)

    @patch.dict(os.environ, {"ITHACA_SHARD_MIN_ROWS_PER_CHUNK": "8"})
    def test_min_rows_per_chunk_env_override(self):
        self.assertEqual(IthacaShardSettings().MIN_ROWS_PER_CHUNK, 8)
