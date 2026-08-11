"""HTTP client for the standalone Ithaca inference service.

Inference used to run in this process. It now lives behind an on-demand GPU
service, and this client is what replaced it: the method names, signatures and
return types match the old `IthacaService` exactly, so the routers call it the
same way they always did.

Two behaviours matter more than the transport:

* **It never raises for an unreachable service.** Every failure -- timeout,
  connection refused, 5xx, malformed body -- comes back as a result object with
  ``available=False`` and a message. That is the same shape the routers already
  returned when a model file was missing, so the frontend needed no change, and
  it follows the logs-and-continues rule the rest of the app is built on.

* **Cold starts are normal, not exceptional.** The service scales to zero, so a
  first request after an idle period pays instance start plus checkpoint load.
  The timeout is sized for that, not for a warm response.
"""

import logging
import time
from typing import Any, Dict, Literal, Optional

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from config import settings
from services.ithaca_models import (
    AttributionResult,
    ContextualizationResult,
    LocationPrediction,
    RestorationCandidate,
    RestorationResult,
    SimilarInscription,
)

logger = logging.getLogger(__name__)

Language = Literal["greek", "latin"]

# Kept in step with the inference service, which enforces them with
# Field(ge=..., le=...). Duplicated rather than imported because that project
# is a separate deployable; the routers validate against these so an
# out-of-range value is a 422 here instead of a round trip that 422s there.
DEFAULT_BEAM_WIDTH = 35
MAX_BEAM_WIDTH = 100
DEFAULT_MAX_RESTORATION_LEN = 15
MAX_RESTORATION_LEN = 20
MAX_TOP_K = 100

# Refresh an ID token this many seconds before it actually expires, so a token
# that is valid when checked cannot expire in flight on a slow request.
_TOKEN_EXPIRY_SKEW = 300.0


class IthacaClient:
    """Calls the inference service, degrading to `available=False` on failure."""

    def __init__(self) -> None:
        self._base_url = settings.ithaca_service.URL.rstrip("/")
        self._timeout = settings.ithaca_service.TIMEOUT
        self._transport = google_requests.Request()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # -- auth ---------------------------------------------------------------

    def _audience(self) -> str:
        """The `aud` claim the service expects.

        Falls back to the base URL, which is what Cloud Run wants when no
        custom audience is configured. It must have no path component -- a
        trailing path is the usual cause of a 401 that looks like a
        credentials problem but is an audience mismatch.
        """
        return settings.ithaca_service.AUDIENCE or self._base_url

    def _auth_headers(self) -> Dict[str, str]:
        """Bearer header, or empty when auth is not in play.

        Returns no header rather than raising when a token cannot be minted:
        locally there is no metadata server, and the service skips
        verification in DEBUG anyway. A genuine production failure surfaces as
        the 401 from the service, which the caller already degrades on.
        """
        if settings.misc.DEBUG:
            return {}

        if self._token and time.monotonic() < self._token_expiry:
            return {"Authorization": f"Bearer {self._token}"}

        try:
            token = id_token.fetch_id_token(self._transport, self._audience())
        except (GoogleAuthError, OSError) as exc:
            logger.warning(f"Could not mint an ID token for the Ithaca service: {exc}")
            return {}

        claims = id_token.verify_oauth2_token(
            token, self._transport, audience=self._audience()
        )
        # `exp` is epoch seconds, but the cache is checked against
        # time.monotonic(), which has an unrelated origin and is immune to
        # clock adjustments. Convert the remaining lifetime into a monotonic
        # deadline rather than comparing the two clocks directly.
        lifetime = float(claims["exp"]) - time.time()
        self._token = token
        self._token_expiry = time.monotonic() + max(0.0, lifetime - _TOKEN_EXPIRY_SKEW)
        return {"Authorization": f"Bearer {token}"}

    # -- transport ----------------------------------------------------------

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST and return the decoded body, or None if anything went wrong.

        None is the single "it did not work" signal; each public method turns
        it into the right shape of degraded result.
        """
        try:
            response = httpx.post(
                f"{self._base_url}{path}",
                json=payload,
                timeout=self._timeout,
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"Ithaca service returned {exc.response.status_code} for {path}"
            )
        except httpx.RequestError as exc:
            logger.warning(f"Ithaca service unreachable for {path}: {exc}")
        except ValueError as exc:
            logger.warning(
                f"Ithaca service returned a malformed body for {path}: {exc}"
            )
        return None

    # -- status -------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Per-language availability, matching the old in-process shape.

        Reports both languages unavailable when the service cannot be reached,
        which is what the endpoint should say: from a caller's point of view an
        unreachable model and an unloaded one are the same thing.
        """
        try:
            response = httpx.get(f"{self._base_url}/health", timeout=10.0)
            response.raise_for_status()
            return response.json().get("models", _unavailable_status())
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(f"Ithaca service health check failed: {exc}")
            return _unavailable_status()

    def is_available(self, language: Language) -> bool:
        """Whether the service can currently serve this language."""
        return bool(self.get_status().get(language, {}).get("available", False))

    # -- inference ----------------------------------------------------------

    def restore(
        self,
        text: str,
        language: Language = "greek",
        beam_width: int = DEFAULT_BEAM_WIDTH,
        temperature: float = 1.0,
        max_restoration_len: int = DEFAULT_MAX_RESTORATION_LEN,
    ) -> RestorationResult:
        """Restore missing characters marked with '?' or '#'."""
        body = self._post(
            "/restore",
            {
                "text": text,
                "language": language,
                "beam_width": beam_width,
                "temperature": temperature,
                "max_restoration_len": max_restoration_len,
            },
        )

        if body is None:
            return RestorationResult(
                input_text=text,
                top_prediction=text,
                missing_indices=[],
                predictions=[],
                available=False,
                message=_UNREACHABLE,
            )

        return RestorationResult(
            input_text=body["input_text"],
            top_prediction=body["top_prediction"],
            missing_indices=body["missing_indices"],
            predictions=[
                RestorationCandidate(
                    text=p["text"],
                    restored_indices=p["restored_indices"],
                    score=p["score"],
                )
                for p in body["predictions"]
            ],
            prediction_saliency=body.get("prediction_saliency", []),
            available=body.get("available", True),
            message=body.get("message"),
        )

    def attribute(self, text: str, language: Language = "greek") -> AttributionResult:
        """Predict date and geographic origin."""
        body = self._post("/attribute", {"text": text, "language": language})

        if body is None:
            return AttributionResult(
                input_text=text,
                locations=[],
                year_scores=[0.0] * 160,
                date_saliency=[],
                location_saliency=[],
                available=False,
                message=_UNREACHABLE,
            )

        return AttributionResult(
            input_text=body["input_text"],
            locations=[
                LocationPrediction(
                    location_id=loc["location_id"],
                    name=loc["name"],
                    score=loc["score"],
                )
                for loc in body["locations"]
            ],
            year_scores=body["year_scores"],
            date_saliency=body["date_saliency"],
            location_saliency=body["location_saliency"],
            predicted_date_range=body.get(
                "predicted_date_range", {"min": None, "max": None, "confidence": 0.0}
            ),
            available=body.get("available", True),
            message=body.get("message"),
        )

    def contextualize(
        self, text: str, language: Language = "greek", top_k: int = 20
    ) -> ContextualizationResult:
        """Find similar inscriptions in the training corpus."""
        body = self._post(
            "/contextualize",
            {"text": text, "language": language, "top_k": top_k},
        )

        if body is None:
            return ContextualizationResult(
                similar=[], available=False, message=_UNREACHABLE
            )

        return ContextualizationResult(
            similar=[
                SimilarInscription(
                    id=str(s["id"]),
                    ids_alt=s.get("ids_alt"),
                    text=s["text"],
                    location_id=s.get("location_id"),
                    date_min=s.get("date_min"),
                    date_max=s.get("date_max"),
                    score=s["score"],
                    partner_link=s.get("partner_link"),
                )
                for s in body["similar"]
            ],
            available=body.get("available", True),
            message=body.get("message"),
        )


_UNREACHABLE = (
    "The inscription model service is currently unavailable. "
    "It may be starting up -- retry in a moment."
)


def _unavailable_status() -> Dict[str, Any]:
    """The status body to report when the service cannot be reached."""
    return {
        "greek": {"available": False, "model_name": "Ithaca"},
        "latin": {"available": False, "model_name": "Aeneas"},
    }


_client: Optional[IthacaClient] = None


def get_ithaca_client() -> IthacaClient:
    """Process-wide client.

    Not `lru_cache`d like the service it replaced: the cached ID token is
    mutable state, and a plain module global makes it obvious that resetting it
    in tests means reassigning this.
    """
    global _client
    if _client is None:
        _client = IthacaClient()
    return _client
