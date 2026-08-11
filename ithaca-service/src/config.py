"""Configuration for the standalone Ithaca inference service.

Deliberately minimal. The backend's `config.py` composes database, auth and LLM
settings and calls `validate_production()`, none of which belong on an
inference node -- importing it here would drag a Postgres driver and Google
OAuth credentials onto a machine whose only job is a forward pass.

Only two groups exist: where the model files live, and how callers authenticate.
"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class AssetSettings(BaseSettings):
    """Where the checkpoints and datasets live.

    Matches the backend's `AssetSettings.INSCRIPTIONS_DIR` name and default so
    the same env var works in both projects during the migration. The GPU image
    bakes the files in at this path; local runs point it at a host directory.
    """

    INSCRIPTIONS_DIR: str = "/app/assets/inscriptions"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class ServiceSettings(BaseSettings):
    """Auth and runtime behaviour for the inference endpoints.

    Cloud Run rejects unauthenticated callers before the request reaches this
    container, so token verification here is defence in depth rather than the
    only gate. It is skipped entirely when DEBUG is on, which is what lets the
    compose stack talk to this service without GCP credentials -- the same
    bargain the backend already makes in `middleware/auth.py`.
    """

    DEBUG: bool = False

    # The Cloud Run service URL, used as the expected `aud` claim. Must be the
    # bare service URL with no path: a trailing path is the usual cause of a
    # 401 that looks like a credentials problem but is an audience mismatch.
    AUDIENCE: str = ""

    # Service accounts permitted to invoke this service. Empty means any caller
    # holding a token with the right audience is accepted, which is safe only
    # because Cloud Run IAM has already filtered on roles/run.invoker.
    ALLOWED_SERVICE_ACCOUNTS: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="ITHACA_",
    )


class Settings:
    """Composition root, mirroring the backend's plain-class pattern."""

    def __init__(self) -> None:
        self.assets = AssetSettings()
        self.service = ServiceSettings()


settings = Settings()
