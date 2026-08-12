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
    # unsupported character). Without these the router reported every failure
    # as a success whose prediction happened to equal the input.
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

    @property
    def predicted_date_range(self) -> dict[str, Any]:
        """Extract the most likely date range from year_scores"""
        if not self.year_scores:
            return {"min": None, "max": None, "confidence": 0.0}

        # Years from -800 to +800 in 10-year intervals
        years = list(range(-800, 810, 10))

        # Find peak
        max_idx = self.year_scores.index(max(self.year_scores))
        max_score = self.year_scores[max_idx]

        # Find range where score > 50% of max
        threshold = max_score * 0.5
        indices_above = [i for i, s in enumerate(self.year_scores) if s >= threshold]

        if indices_above:
            min_year = years[min(indices_above)]
            max_year = years[max(indices_above)]
            return {"min": min_year, "max": max_year, "confidence": max_score}

        return {"min": years[max_idx], "max": years[max_idx], "confidence": max_score}


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
