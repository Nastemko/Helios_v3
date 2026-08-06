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


class IthacaShardSettings(BaseSettings):
    """Distributed Ithaca inference settings.

    Beam search runs one forward pass per generation over a batch of
    ``beam_width`` candidate rows, and every row is independent through the
    model. Splitting that batch across machines is bit-exact, so it buys
    latency without changing predictions.

    Adding cores to one box does not help: the forward pass is ~49% serial and
    saturates at ~2 cores (measured 1->19.93s, 2->13.17s, 4->12.94s at beam 35).
    Sharding sidesteps that serial section because each node runs a full,
    independent forward pass.

    Empty URLS (the default) disables sharding entirely and restores the
    single-process path exactly.
    """

    # The *remote* workers only. The coordinator always takes a slice itself,
    # so two URLs here means a three-node cluster.
    URLS: list[str] = []

    # Per-generation deadline. Must stay well under the service's overall
    # time budget so a hung shard falls back locally instead of consuming the
    # whole restoration budget.
    TIMEOUT: float = 60.0

    # Skip the fan-out unless every node gets at least this many rows. Per-row
    # cost is flat (~290ms) down to batch 4 but collapses below it (483ms at
    # batch 2, 529ms at batch 1), so tiny slices waste both compute and a
    # round trip. The '#' expansion tail is what trips this.
    MIN_ROWS_PER_NODE: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="ITHACA_SHARD_",
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
        self.ithaca_shard = IthacaShardSettings()

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
