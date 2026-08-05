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
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import jax

from config import settings
from services.ithaca_service.models import (
    AttributionResult,
    ContextualizationResult,
    LocationPrediction,
    RestorationCandidate,
    RestorationResult,
    SimilarInscription,
)
from vendor.predictingthepast.eval import inference
from vendor.predictingthepast.models.model import Model
from vendor.predictingthepast.util import alphabet as util_alphabet

logger = logging.getLogger(__name__)

# Type alias for supported languages
Language = Literal["greek", "latin"]

# Restoration cost scales roughly linearly with beam width, and the value was
# previously taken straight from the request body with no bound -- a client could
# ask for arbitrarily much compute. Measured on 4 cores over three fixtures
# (src/scripts/bench_ithaca.py), total wall time:
#   beam 100 -> 337.1s   50 -> 195.5s   35 -> 172.8s   20 -> 130.4s
#
# 35 is the default: ~2x faster than 100, and it scored >= beam 100 on the top
# prediction for every fixture. Note that a wider beam is NOT automatically
# better here -- beam search is non-monotonic in width, because candidates are
# pruned by length-normalised score (logprob / (1+len)^a_penalty, see
# util/eval.py) while the score returned to callers is raw exp(logprob). Beam
# 100 came last or tied-last on all three fixtures.
#
# Caveat: those fixtures are synthetic and scored by the model's own likelihood,
# which measures self-consistency, not correctness. Re-tune against inscriptions
# with known restorations before treating this as an accuracy-optimal value.
DEFAULT_BEAM_WIDTH = 35
MAX_BEAM_WIDTH = 100

# A '#' (unknown-length gap) is far more expensive than a '?' (single missing
# character), because it searches over how long the gap is *as well as* what
# fills it: each expansion step re-adds a '#' at the next position, so the branch
# repeats up to max_restoration_len times. Traced on the same fixtures at beam
# 35 -- one '#' takes 30 forward passes over 15 distinct sequence lengths, while
# nine '?' take 9 passes at one fixed length (and six '?' take only 6, since
# separate slots fill in parallel).
#
# Cost is NOT simply linear in this value. Swept on the '#' fixture at beam 35
# (wall time / restored fill):
#   mrl=3  -> 30.1s / "τωι"    (3 chars, capped)
#   mrl=5  -> 23.0s / "ειπεν"  (5 chars, capped)
#   mrl=8  -> 38.8s / "επειδη" (6 chars, not capped)
#   mrl=15 -> 87.7s / "επειδη" (6 chars, not capped)
#
# Two effects: headroom past the answer the model actually wants is still
# searched and still costs (15 is ~2.3x the cost of 8 for an identical answer),
# but a cap *below* that answer is not simply cheaper either -- it forces the
# beam into worse-fitting short candidates that survive longer, which is why
# mrl=3 costs more than mrl=5. The cheapest point is a cap just above the true
# gap length.
#
# It is a *semantic* cap, not just a compute knob -- it declares the longest gap
# the model may propose, so lowering it makes longer lacunae unrestorable. The
# default therefore stays at the upstream 15 (safe for any gap) and is exposed
# to callers, who are the ones who can see how big the lacuna actually is.
DEFAULT_MAX_RESTORATION_LEN = 15
# Upstream UNK_RESTORATION_MAX_LEN; inference.restore raises above this.
MAX_RESTORATION_LEN = 20

# How many characters the beam search expands at each hole. Upstream tries the
# whole alphabet -- 29 branches for Greek (26 letters + final sigma/koppa/stigma
# + numeral '0', plus space) -- and builds a full string, a join and a set copy
# for every one, beam_width times per generation. Only a handful ever survive
# the length-normalised pruning at the end of the iteration, so the rest is
# wasted allocation.
#
# 8 keeps every character with any realistic chance of surviving while cutting
# candidate construction ~3.6x. Set to None to restore exhaustive upstream
# behaviour if a restoration ever looks truncated.
DEFAULT_TOP_CHARS = 8

# Backstop for the failure this whole module was tuned to prevent: one request
# held a worker for 947s, and since _inference_lock serialises inference, that
# request also blocked every other user's restore behind it.
#
# Checked between generations, so the real ceiling is this plus one forward
# pass. Completed candidates found before expiry are still returned, so hitting
# the budget degrades the answer rather than failing the request. It is
# deliberately well above the expected cost of a legitimate restoration -- it
# exists to bound the pathological case, not to trim normal ones.
DEFAULT_TIME_BUDGET_SECONDS = 180.0


def _failure_message(error: Exception, language: Language) -> str:
    """Turn an inference exception into something a reader can act on.

    The vendored tokenizer looks characters up in ``alphabet.char2idx`` with no
    fallback, so anything outside the model's alphabet raises KeyError rather
    than a descriptive ValueError. Latin in particular has no 'j' or 'w', and
    neither alphabet has ',' or ';'.
    """
    if isinstance(error, KeyError):
        return (
            f"Unsupported character for the {language} model: {error}. "
            "Only the model's alphabet, spaces, '.', '?' and '#' are accepted."
        )
    return str(error)


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
        except Exception as e:
            logger.error(f"Failed to initialize {self.language} model: {e}")

        # NB: this return is deliberately NOT inside a `finally`. A `return` in
        # `finally` swallows every exception raised in the try -- including
        # MemoryError and KeyboardInterrupt -- so a failed load degraded to
        # `available: false` with no traceback and no way to interrupt it.
        return self.initialized

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
        # One inference at a time: a single restore already saturates the CPUs
        # this runs on, so concurrent requests only cause cache thrashing. The
        # routers acquire this non-blocking and return 429 rather than queueing.
        self._inference_lock = threading.Semaphore(1)

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
        # Loading a checkpoint costs a pickle read plus the dataset and
        # retrieval embeddings. Skip it when this language is already live.
        cached = self._models.get(language)
        if cached is not None and cached.is_available:
            logger.info(
                f"{language.upper()} model already initialized; skipping reload"
            )
            return True

        # Default paths
        models_dir = Path(settings.assets.INSCRIPTIONS_DIR) / "models"

        if checkpoint_path is None:
            if language == "greek":
                checkpoint_path = models_dir / "ithaca_153143996_2.pkl"
            else:
                checkpoint_path = models_dir / "aeneas_117149994_2.pkl"

        if dataset_path is None:
            if language == "greek":
                dataset_path = Path(settings.assets.INSCRIPTIONS_DIR) / "iphi.json"
            else:
                dataset_path = Path(settings.assets.INSCRIPTIONS_DIR) / "led.json"

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
        beam_width: int = DEFAULT_BEAM_WIDTH,
        temperature: float = 1.0,
        max_restoration_len: int = DEFAULT_MAX_RESTORATION_LEN,
        top_chars: Optional[int] = DEFAULT_TOP_CHARS,
        time_budget: Optional[float] = DEFAULT_TIME_BUDGET_SECONDS,
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
                top_chars=top_chars,
                time_budget=time_budget,
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

        except (ValueError, KeyError) as e:
            logger.warning(f"Restoration failed for {language}: {e}")
            return RestorationResult(
                input_text=text,
                top_prediction=text,
                missing_indices=[],
                predictions=[],
                available=False,
                message=_failure_message(e, language),
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

        except (ValueError, KeyError) as e:
            logger.warning(f"Attribution failed for {language}: {e}")
            return AttributionResult(
                input_text=text,
                locations=[],
                year_scores=[0.0] * 160,
                date_saliency=[],
                location_saliency=[],
                available=False,
                message=_failure_message(e, language),
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
                        partner_link=(
                            result.partner_link[i] if result.partner_link else None
                        ),
                    )
                )

            return ContextualizationResult(similar=similar)

        except (ValueError, KeyError) as e:
            logger.warning(f"Contextualization failed for {language}: {e}")
            return ContextualizationResult(
                similar=[],
                available=False,
                message=_failure_message(e, language),
            )


@lru_cache(maxsize=1)
def get_ithaca_service() -> IthacaService:
    """Get or create the Ithaca service singleton"""
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
