"""Caller verification for the inference endpoints.

Cloud Run is the primary gate: the service is deployed with
`--no-allow-unauthenticated`, so a request without a valid `roles/run.invoker`
identity is rejected by the platform and never reaches this process. What
follows is a second layer -- it confirms the token was minted for *this*
service rather than merely for some Cloud Run service the caller can reach.

The whole check is skipped when DEBUG is on. That is what lets the compose
stack run offline with no GCP credentials, and it mirrors the bargain the
backend already makes in `middleware/auth.py`.
"""

import logging

from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from config import settings

logger = logging.getLogger(__name__)

# One transport, reused. Building a Request per call opens a fresh connection
# to Google's certificate endpoint; the library caches the signing keys on the
# transport, so sharing it keeps verification to a local signature check.
_transport = google_requests.Request()


def validate_auth_config() -> None:
    """Fail startup when auth is on but unconfigured.

    Called from the app's lifespan. An empty audience would make
    `verify_oauth2_token` accept a token minted for *any* Cloud Run service the
    caller can reach, so it cannot be allowed to pass -- but failing per-request
    turns a deployment mistake into a 500 on every inference call, discovered
    only when a user tries one. Refusing to boot surfaces it at deploy time,
    which is the same bargain the backend makes in `validate_production()`.
    """
    if settings.service.DEBUG:
        logger.warning(
            "ITHACA_DEBUG is on: caller tokens are NOT verified. "
            "This is for local development only."
        )
        return

    if not settings.service.AUDIENCE:
        raise ValueError(
            "ITHACA_AUDIENCE must be set when ITHACA_DEBUG is False. "
            "It is the expected 'aud' claim on caller ID tokens, and must be "
            "this service's bare URL with no path component."
        )


def verify_caller(authorization: str = Header(default="")) -> None:
    """Reject anything that is not a valid ID token for this service.

    Raises 401 rather than 403: the caller's identity could not be established,
    which is distinct from an established identity lacking permission.

    `validate_auth_config` has already guaranteed an audience is configured, so
    there is no misconfiguration branch to handle here.
    """
    if settings.service.DEBUG:
        return

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Expected an 'Authorization: Bearer <token>' header.",
        )

    try:
        claims = id_token.verify_oauth2_token(
            token, _transport, audience=settings.service.AUDIENCE
        )
    except ValueError as exc:
        # Covers expiry, bad signature, and audience mismatch. The message is
        # logged but not returned: it can name the expected audience, which is
        # not something to hand an unauthenticated caller.
        logger.warning(f"Rejected caller token: {exc}")
        raise HTTPException(status_code=401, detail="Invalid credentials.") from exc

    allowed = settings.service.ALLOWED_SERVICE_ACCOUNTS
    if allowed and claims.get("email") not in allowed:
        logger.warning(f"Rejected caller {claims.get('email')!r}: not in allowlist")
        raise HTTPException(status_code=403, detail="Caller not permitted.")
