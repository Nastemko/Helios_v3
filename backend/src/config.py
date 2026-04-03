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

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback/google"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class OpenRouterSettings(BaseSettings):
    """OpenRouter LLM configuration for cloud-based inference via OpenAI SDK"""

    API_KEY: str = ""
    BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    TEMPERATURE: float = 0.1
    MAX_TOKENS: int = 4096

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="OPENROUTER_",
    )


class MiscSettings(BaseSettings):
    """Application settings composed from component settings"""

    # Application
    APP_NAME: str = "Helios API"
    DEBUG: bool = True  # Set to False in production

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
        self.openrouter = OpenRouterSettings()
        self.database = DatabaseSettings()
        self.assets = AssetSettings()


settings = Settings()
