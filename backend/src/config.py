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


class DatabaseSettings(BaseSettings):
    """Database configuration settings"""

    # PostgreSQL Settings (for production)
    HOST: str = "localhost"
    PORT: int = 5432
    DB: str = "helios"
    USER: str = "heliosuser"
    PASSWORD: str = ""
    POOL_SIZE: int = 20
    MAX_OVERFLOW: int = 40
    POOL_TIMEOUT: int = 30
    POOL_RECYCLE: int = 3600
    CONNECT_TIMEOUT: int = 10

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

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SESSION_MAX_AGE: int = 3600
    SLOW_REQUEST_THRESHOLD: float = 0.5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class IthacaSettings(BaseSettings):
    """In-process Ithaca/Aeneas inference behaviour."""

    # Soft wall-clock cap per restore, enforced between beam-search
    # generations (real ceiling = this + one forward pass). Completed
    # candidates found before expiry are still returned. One request holds
    # _inference_lock, so this also bounds how long every other restore waits.
    TIME_BUDGET: float = 180.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="ITHACA_",
    )


class PaginationSettings(BaseSettings):
    """Pagination defaults and maxima for list endpoints."""

    DEFAULT_TEXTS_LIMIT: int = 50
    MAX_TEXTS_LIMIT: int = 100
    DEFAULT_SEGMENTS_LIMIT: int = 1000
    MAX_SEGMENTS_LIMIT: int = 5000
    DEFAULT_INSCRIPTIONS_LIMIT: int = 50
    MAX_INSCRIPTIONS_LIMIT: int = 200
    DEFAULT_ANNOTATIONS_LIMIT: int = 100
    MAX_ANNOTATIONS_LIMIT: int = 500
    MOST_ANNOTATED_TOP_N: int = 10
    LIST_PREVIEW_CHARS: int = 150

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="PAGINATION_",
    )


class Settings:
    def __init__(self, **kwargs):
        self.misc = MiscSettings()
        self.auth = AuthSettings()
        self.llm = LLMSettings()
        self.database = DatabaseSettings()
        self.assets = AssetSettings()
        self.ithaca = IthacaSettings()
        self.pagination = PaginationSettings()

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
