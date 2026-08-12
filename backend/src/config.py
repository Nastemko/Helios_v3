"""Application configuration"""

from enum import StrEnum, auto

from pydantic_settings import BaseSettings, SettingsConfigDict


class ThinkLevel(StrEnum):
    none = auto()
    low = auto()
    medium = auto()
    high = auto()
    xhigh = auto()


class LLMSettings(BaseSettings):
    """LLM configuration settings"""

    BASE_URL: str = "http://localhost:11434/v1"
    MODEL: str = "llama3.2:3b"
    API_KEY: str = "ollama"  # Placeholder for Ollama; required for other providers
    TEMPERATURE: float = 0.2
    THINK: ThinkLevel = ThinkLevel.none
    TIMEOUT: int = 120  # 2 minutes for inference
    ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="LLM_",
    )


class IthacaServiceSettings(BaseSettings):
    """Where to reach the Ithaca inference service.

    Inference no longer runs in this process. It lives in its own deployable
    (``ithaca-service/``) so that JAX, the Flax model code and ~2GB of
    checkpoints stay off the API image, and so the model can sit on an
    accelerator that scales to zero while the API does not.

    An unreachable service is a degraded feature, not an error: the client
    returns ``available=False`` and the inscription endpoints report the model
    as unavailable, exactly as they did when a checkpoint file was missing.
    """

    URL: str = "http://ithaca:8001"

    # Sized for a cold start, not a warm call. The service scales to zero, so
    # a first request pays instance start plus a multi-second checkpoint load
    # before inference begins. It must also exceed the service's own
    # restoration time budget (180s) so a slow-but-working restore is waited
    # out rather than abandoned, and stay under the platform request timeout.
    TIMEOUT: float = 240.0

    # Expected `aud` claim on the ID token sent to the service. Empty means
    # "use URL", which is what Cloud Run wants unless a custom audience is
    # configured. Must never carry a path component -- an audience with a path
    # is the usual cause of a 401 that reads like a credentials failure.
    AUDIENCE: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="ITHACA_SERVICE_",
    )


class DatabaseSettings(BaseSettings):
    """Database configuration settings"""

    # PostgreSQL Settings (for production)
    HOST: str = "localhost"
    PORT: int = 5432
    DB: str = "helios"
    USER: str = "heliosuser"
    PASSWORD: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="DATABASE_",
    )


class AssetSettings(BaseSettings):
    """Asset configuration settings for Perseus and ML models"""

    # ML models
    INSCRIPTIONS_DIR: str = "/app/assets/inscriptions"

    # Perseus texts
    # In Docker: /app/data/canonical-greekLit/data
    # Local development: ../canonical-greekLit/data
    PERSEUS_DATA_DIR: str = "/app/assets/canonical-greekLit/data"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class AuthSettings(BaseSettings):
    """Authentication and authorization configuration settings"""

    # Security - MUST be overridden in .env for production
    SECRET_KEY: str = ""
    # The JWT algorithm is deliberately not configurable: see JWT_ALGORITHM in
    # utils/security.py.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback/google"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class MiscSettings(BaseSettings):
    """Application settings composed from component settings"""

    # Application
    APP_NAME: str = "Helios API"
    DEBUG: bool = False  # Set to True only for local development

    # CORS - include multiple ports for development flexibility
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class Settings:
    def __init__(self, **kwargs):
        self.misc = MiscSettings()
        self.auth = AuthSettings()
        self.llm = LLMSettings()
        self.database = DatabaseSettings()
        self.assets = AssetSettings()
        self.ithaca_service = IthacaServiceSettings()

    def validate_production(self) -> None:
        """
        Call this at startup to validate production-ready configuration.

        When DEBUG is off, Google OAuth is the only way to authenticate, so the
        signing key and both Google credentials are all mandatory. Without them
        the app would boot but no one could ever log in.
        """
        if self.misc.DEBUG:
            return

        missing = [
            name
            for name, value in (
                ("SECRET_KEY", self.auth.SECRET_KEY),
                ("GOOGLE_CLIENT_ID", self.auth.GOOGLE_CLIENT_ID),
                ("GOOGLE_CLIENT_SECRET", self.auth.GOOGLE_CLIENT_SECRET),
            )
            if not value
        ]

        if missing:
            raise ValueError(
                f"{', '.join(missing)} must be set in .env when DEBUG=False. "
                "Google OAuth is the only authentication method in production. "
                "Generate a SECRET_KEY with: openssl rand -hex 32"
            )


settings = Settings()
