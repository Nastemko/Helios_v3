"""Result shapes returned by the Ithaca inference service.

These mirror the dataclasses that used to live in
`services/ithaca_service/models.py`, before inference moved to its own service.
They are kept here, rather than imported from that project, because the two now
deploy as separate images -- the backend must be able to describe a restoration
result without depending on anything that pulls in JAX.

Any change here is a wire-contract change and must land in both projects.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LocationPrediction:
    """Predicted geographic location with confidence score"""

    location_id: int
    name: str
    score: float


@dataclass
class RestorationCandidate:
    """A candidate restoration from beam search"""

    text: str
    restored_indices: list[int]
    score: float


@dataclass
class RestorationResult:
    """Result from text restoration"""

    input_text: str
    top_prediction: str
    missing_indices: list[int]
    predictions: list[RestorationCandidate]
    prediction_saliency: list[dict[str, Any]] = field(default_factory=list)
    # False when inference declined the input (too short, no gap markers,
    # unsupported character) or when the inference service could not be
    # reached. Without these the router reported every failure as a success
    # whose prediction happened to equal the input.
    available: bool = True
    message: str | None = None


@dataclass
class AttributionResult:
    """Result from date/location attribution"""

    input_text: str
    locations: list[LocationPrediction]
    year_scores: list[float]  # 160 values for years -800 to +800 (10-year intervals)
    date_saliency: list[float]
    location_saliency: list[float]
    available: bool = True
    message: str | None = None
    # Sent by the inference service, which computes it from year_scores. Held
    # as a plain field here rather than the property it used to be: the value
    # now arrives over the wire, and recomputing it locally would be a second
    # implementation of the same rule that could silently drift.
    predicted_date_range: dict[str, Any] = field(
        default_factory=lambda: {"min": None, "max": None, "confidence": 0.0}
    )


@dataclass
class SimilarInscription:
    """A similar inscription from contextualization"""

    id: str
    ids_alt: Optional[dict[str, str]]
    text: str
    location_id: Optional[int]
    date_min: Optional[int]
    date_max: Optional[int]
    score: float
    partner_link: Optional[str] = None


@dataclass
class ContextualizationResult:
    """Result from finding similar inscriptions"""

    similar: list[SimilarInscription]
    available: bool = True
    message: str | None = None
