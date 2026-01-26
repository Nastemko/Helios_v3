"""
Ithaca Model Service - Integration with Predicting the Past model

This service wraps the Ithaca/Aeneas model for:
- Text restoration (filling in missing characters)
- Attribution (predicting date and geographic origin)
- Contextualization (finding similar inscriptions)

Supports both Greek (Ithaca) and Latin (Aeneas) models simultaneously.
"""

import logging
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import jax

from vendor.predictingthepast.eval import inference
from vendor.predictingthepast.models.model import Model
from vendor.predictingthepast.util import alphabet as util_alphabet

logger = logging.getLogger(__name__)


# Type alias for supported languages
Language = Literal["greek", "latin"]


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
    restored_indices: List[int]
    score: float


@dataclass
class RestorationResult:
    """Result from text restoration"""

    input_text: str
    top_prediction: str
    missing_indices: List[int]
    predictions: List[RestorationCandidate]
    prediction_saliency: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AttributionResult:
    """Result from date/location attribution"""

    input_text: str
    locations: List[LocationPrediction]
    year_scores: List[float]  # 160 values for years -800 to +800 (10-year intervals)
    date_saliency: List[float]
    location_saliency: List[float]

    @property
    def predicted_date_range(self) -> Dict[str, Any]:
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
    ids_alt: Optional[Dict[str, str]]
    text: str
    location_id: Optional[int]
    date_min: Optional[int]
    date_max: Optional[int]
    score: float
    partner_link: Optional[str] = None


@dataclass
class ContextualizationResult:
    """Result from finding similar inscriptions"""

    similar: List[SimilarInscription]


class IthacaModel:
    """
    Single model instance for one language (Greek or Latin).
    """

    def __init__(self, language: Language):
        self.language = language
        self.initialized = False
        self.forward = None
        self.params = None
        self.alphabet = None
        self.region_map = None
        self.dataset = None
        self.retrieval = None
        self.vocab_char_size = None

    def initialize(
        self,
        checkpoint_path: Path,
        dataset_path: Path,
        retrieval_path: Path,
    ) -> bool:
        """
        Initialize the model with checkpoint and data files.
        """
        try:
            logger.info(f"Initializing {self.language.upper()} model...")

            # Load checkpoint
            logger.info(f"Loading checkpoint from {checkpoint_path}...")
            with open(checkpoint_path, "rb") as f:
                checkpoint = pickle.load(f)

            # Extract model components
            self.params = jax.device_put(checkpoint["params"])
            model = Model(**checkpoint["model_config"])
            self.forward = model.apply
            self.region_map = checkpoint["region_map"]
            self.vocab_char_size = checkpoint["model_config"]["vocab_char_size"]

            # Initialize alphabet
            if self.language == "latin":
                self.alphabet = util_alphabet.LatinAlphabet()
            else:
                self.alphabet = util_alphabet.GreekAlphabet()

            # Load dataset for contextualization
            logger.info(f"Loading dataset from {dataset_path}...")
            self.dataset = inference.load_dataset(str(dataset_path))

            # Load retrieval embeddings
            logger.info(f"Loading retrieval embeddings from {retrieval_path}...")
            self.retrieval = inference.load_retrieval(str(retrieval_path))

            self.initialized = True
            logger.info(f"{self.language.upper()} model initialized successfully!")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize {self.language} model: {e}")
            self.initialized = False
            return False

    @property
    def is_available(self) -> bool:
        """Check if the model is ready for inference"""
        return self.initialized and self.forward is not None


class IthacaService:
    """
    Service for Ithaca/Aeneas model inference.

    Supports both Greek and Latin models loaded simultaneously.
    """

    def __init__(self):
        self._models: Dict[Language, IthacaModel] = {}

    def initialize_model(
        self,
        language: Language,
        checkpoint_path: Optional[Path] = None,
        dataset_path: Optional[Path] = None,
        retrieval_path: Optional[Path] = None,
    ) -> bool:
        """
        Initialize a specific language model.
        """
        # Default paths
        models_dir = Path(__file__).parent.parent.parent / "models"

        if checkpoint_path is None:
            if language == "greek":
                checkpoint_path = models_dir / "ithaca_153143996_2.pkl"
            else:
                checkpoint_path = models_dir / "aeneas_117149994_2.pkl"

        if dataset_path is None:
            if language == "greek":
                dataset_path = models_dir / "iphi.json"
            else:
                dataset_path = models_dir / "led.json"

        if retrieval_path is None:
            if language == "greek":
                retrieval_path = models_dir / "iphi_emb_xid153143996.pkl"
            else:
                retrieval_path = models_dir / "led_emb_xid117149994.pkl"

        # Check if files exist
        if not checkpoint_path.exists():
            logger.warning(f"Checkpoint not found: {checkpoint_path}")
            return False
        if not dataset_path.exists():
            logger.warning(f"Dataset not found: {dataset_path}")
            return False
        if not retrieval_path.exists():
            logger.warning(f"Retrieval file not found: {retrieval_path}")
            return False

        # Create and initialize model
        model = IthacaModel(language)
        success = model.initialize(checkpoint_path, dataset_path, retrieval_path)

        if success:
            self._models[language] = model

        return success

    def get_model(self, language: Language) -> Optional[IthacaModel]:
        """Get a specific language model"""
        return self._models.get(language)

    def is_available(self, language: Language) -> bool:
        """Check if a specific language model is ready"""
        model = self._models.get(language)
        return model is not None and model.is_available

    def get_status(self) -> Dict[str, Any]:
        """Get status of all models"""
        return {
            "greek": {"available": self.is_available("greek"), "model_name": "Ithaca"},
            "latin": {"available": self.is_available("latin"), "model_name": "Aeneas"},
        }

    def restore(
        self,
        text: str,
        language: Language = "greek",
        beam_width: int = 100,
        temperature: float = 1.0,
        max_restoration_len: int = 15,
    ) -> RestorationResult:
        """
        Restore missing characters in an inscription.
        """
        model = self._models.get(language)

        if model is None or not model.is_available:
            logger.warning(f"{language} model not available - returning stub response")
            return RestorationResult(
                input_text=text, top_prediction=text, missing_indices=[], predictions=[]
            )

        try:
            result = inference.restore(
                text,
                forward=model.forward,
                params=model.params,
                alphabet=model.alphabet,
                vocab_char_size=model.vocab_char_size,
                beam_width=beam_width,
                temperature=temperature,
                unk_restoration_max_len=max_restoration_len,
            )

            predictions = [
                RestorationCandidate(
                    text=r.text, restored_indices=r.restored, score=r.score
                )
                for r in result.predictions
            ]

            saliency = [
                {"text": s.text, "restored_idx": s.restored_idx, "saliency": s.saliency}
                for s in result.prediction_saliency
            ]

            return RestorationResult(
                input_text=result.input_text,
                top_prediction=result.top_prediction,
                missing_indices=result.missing,
                predictions=predictions,
                prediction_saliency=saliency,
            )

        except ValueError as e:
            logger.warning(f"Restoration failed: {e}")
            return RestorationResult(
                input_text=text, top_prediction=text, missing_indices=[], predictions=[]
            )

    def attribute(self, text: str, language: Language = "greek") -> AttributionResult:
        """
        Predict date and geographic origin of an inscription.
        """
        model = self._models.get(language)

        if model is None or not model.is_available:
            logger.warning(f"{language} model not available - returning stub response")
            return AttributionResult(
                input_text=text,
                locations=[],
                year_scores=[0.0] * 160,
                date_saliency=[],
                location_saliency=[],
            )

        try:
            result = inference.attribute(
                text,
                forward=model.forward,
                params=model.params,
                alphabet=model.alphabet,
                vocab_char_size=model.vocab_char_size,
            )

            # Convert location predictions with names from region_map
            if not isinstance(model.region_map, dict):
                raise TypeError("model.region_map must be a dictionary")
            names_list = model.region_map.get("names", [])
            locations = []
            for loc in result.locations[:20]:
                if loc.location_id < len(names_list):
                    name = names_list[loc.location_id]
                else:
                    name = f"Region {loc.location_id}"
                locations.append(
                    LocationPrediction(
                        location_id=loc.location_id, name=name, score=loc.score
                    )
                )

            return AttributionResult(
                input_text=result.input_text,
                locations=locations,
                year_scores=result.year_scores,
                date_saliency=result.date_saliency,
                location_saliency=result.location_saliency,
            )

        except ValueError as e:
            logger.warning(f"Attribution failed: {e}")
            return AttributionResult(
                input_text=text,
                locations=[],
                year_scores=[0.0] * 160,
                date_saliency=[],
                location_saliency=[],
            )

    def contextualize(
        self, text: str, language: Language = "greek", top_k: int = 20
    ) -> ContextualizationResult:
        """
        Find similar inscriptions in the corpus.
        """
        model = self._models.get(language)

        if model is None or not model.is_available:
            logger.warning(f"{language} model not available - returning stub response")
            return ContextualizationResult(similar=[])

        try:
            result = inference.contextualize(
                text,
                model.dataset,
                model.retrieval,
                model.forward,
                model.params,
                model.alphabet,
                model.region_map,
                include_test=True,
                top_k=top_k,
            )

            similar = []
            for i in range(len(result.ids)):
                similar.append(
                    SimilarInscription(
                        id=str(result.ids[i]),
                        ids_alt=result.ids_alt[i] if result.ids_alt else None,
                        text=result.text[i],
                        location_id=result.location_ids[i],
                        date_min=result.date_min[i],
                        date_max=result.date_max[i],
                        score=result.score[i],
                        partner_link=result.partner_link[i]
                        if result.partner_link
                        else None,
                    )
                )

            return ContextualizationResult(similar=similar)

        except ValueError as e:
            logger.warning(f"Contextualization failed: {e}")
            return ContextualizationResult(similar=[])


# Singleton instance
_ithaca_service: Optional[IthacaService] = None


def get_ithaca_service() -> IthacaService:
    """Get or create the Ithaca service singleton"""
    global _ithaca_service
    if _ithaca_service is None:
        _ithaca_service = IthacaService()
    return _ithaca_service


def initialize_ithaca_service(language: Language = "greek") -> bool:
    """
    Initialize a specific language model.
    """
    service = get_ithaca_service()
    return service.initialize_model(language)


def initialize_all_models() -> Dict[str, bool]:
    """
    Initialize both Greek and Latin models.
    Returns dict with success status for each.
    """
    service = get_ithaca_service()
    results = {}

    logger.info("Initializing all Ithaca/Aeneas models...")

    # Try Greek
    results["greek"] = service.initialize_model("greek")

    # Try Latin
    results["latin"] = service.initialize_model("latin")

    logger.info(f"Model initialization complete: {results}")
    return results
