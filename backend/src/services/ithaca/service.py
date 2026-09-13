"""Ithaca/Aeneas service facade with async semaphore guard."""

import asyncio
import logging
import pickle
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

import jax

from config import settings
from services.ithaca import inference
from services.ithaca.alphabet import GreekAlphabet, LatinAlphabet
from services.ithaca.model.model import Model
from services.ithaca.schemas import (
    AttributionResult,
    ContextualizationResult,
    LocationPrediction,
    RestorationCandidate,
    RestorationResult,
    SimilarInscription,
)

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


class BusyError(RuntimeError):
    """Raised when an inference is already running (router maps to HTTP 429)."""


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


@dataclass
class _LoadedModel:
    """A single initialized model for one language."""

    language: Language
    forward: Any
    params: Any
    alphabet: Any
    region_map: dict
    dataset: dict
    retrieval: dict
    vocab_char_size: int

    @property
    def is_available(self) -> bool:
        """Check if the model is ready for inference."""
        return self.forward is not None


def _resolve_paths(
    language: Language,
    checkpoint_path: Path | None,
    dataset_path: Path | None,
    retrieval_path: Path | None,
) -> tuple[Path, Path, Path]:
    """Fill in default checkpoint/dataset/retrieval paths for a language."""
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

    return checkpoint_path, dataset_path, retrieval_path


def _load_model(
    language: Language,
    checkpoint_path: Path,
    dataset_path: Path,
    retrieval_path: Path,
) -> Optional[_LoadedModel]:
    """Load checkpoint, alphabet, dataset and retrieval for one language."""
    try:
        logger.info(f"Initializing {language.upper()} model...")

        # Load checkpoint
        logger.info(f"Loading checkpoint from {checkpoint_path}...")
        with open(checkpoint_path, "rb") as f:
            checkpoint = pickle.load(f)

        # Extract model components
        params = jax.device_put(checkpoint["params"])
        model = Model(**checkpoint["model_config"])
        forward = model.apply
        region_map = checkpoint["region_map"]
        vocab_char_size = checkpoint["model_config"]["vocab_char_size"]

        # Initialize alphabet
        if language == "latin":
            alphabet = LatinAlphabet()
        else:
            alphabet = GreekAlphabet()

        # Load dataset for contextualization
        logger.info(f"Loading dataset from {dataset_path}...")
        dataset = inference.load_dataset(str(dataset_path))

        # Load retrieval embeddings
        logger.info(f"Loading retrieval embeddings from {retrieval_path}...")
        retrieval = inference.load_retrieval(str(retrieval_path))

        logger.info(f"{language.upper()} model initialized successfully!")
        return _LoadedModel(
            language=language,
            forward=forward,
            params=params,
            alphabet=alphabet,
            region_map=region_map,
            dataset=dataset,
            retrieval=retrieval,
            vocab_char_size=vocab_char_size,
        )
    except Exception as e:
        logger.error(f"Failed to initialize {language} model: {e}")
        return None


class IthacaService:
    """Service for Ithaca/Aeneas model inference.

    Supports both Greek and Latin models loaded simultaneously.
    """

    def __init__(self) -> None:
        self._models: dict[Language, _LoadedModel] = {}
        # One inference at a time: a single restore already saturates the CPUs
        # this runs on, so concurrent requests only cause cache thrashing. The
        # routers acquire this non-blocking and return 429 rather than queueing.
        self._sem = asyncio.Semaphore(1)

    def initialize_model(
        self,
        language: Language,
        checkpoint_path: Path | None = None,
        dataset_path: Path | None = None,
        retrieval_path: Path | None = None,
    ) -> bool:
        """Initialize a specific language model."""
        # Loading a checkpoint costs a pickle read plus the dataset and
        # retrieval embeddings. Skip it when this language is already live.
        cached = self._models.get(language)
        if cached is not None and cached.is_available:
            logger.info(
                f"{language.upper()} model already initialized; skipping reload"
            )
            return True

        checkpoint_path, dataset_path, retrieval_path = _resolve_paths(
            language, checkpoint_path, dataset_path, retrieval_path
        )

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
        loaded = _load_model(language, checkpoint_path, dataset_path, retrieval_path)

        if loaded is not None:
            self._models[language] = loaded
            return True

        return False

    def get_model(self, language: Language) -> _LoadedModel | None:
        """Get a specific language model."""
        return self._models.get(language)

    def is_available(self, language: Language) -> bool:
        """Check if a specific language model is ready."""
        model = self._models.get(language)
        return model is not None and model.is_available

    def get_status(self) -> dict[str, Any]:
        """Get status of all models."""
        return {
            "greek": {"available": self.is_available("greek"), "model_name": "Ithaca"},
            "latin": {"available": self.is_available("latin"), "model_name": "Aeneas"},
        }

    def restore_sync(
        self,
        text: str,
        language: Language = "greek",
        beam_width: int = DEFAULT_BEAM_WIDTH,
        temperature: float = 1.0,
        max_restoration_len: int = DEFAULT_MAX_RESTORATION_LEN,
        top_chars: Optional[int] = DEFAULT_TOP_CHARS,
        time_budget: Optional[float] = None,
    ) -> RestorationResult:
        """Restore missing characters in an inscription.

        `time_budget=None` (the default) resolves to `settings.ithaca.TIME_BUDGET`
        at call time; there is intentionally no way to request an unbounded
        restore — one request holds `_sem`, so an unbounded search
        would starve every other restore.
        """
        if time_budget is None:
            time_budget = settings.ithaca.TIME_BUDGET
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

    def attribute_sync(
        self, text: str, language: Language = "greek"
    ) -> AttributionResult:
        """Predict date and geographic origin of an inscription."""
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

    def contextualize_sync(
        self, text: str, language: Language = "greek", top_k: int = 20
    ) -> ContextualizationResult:
        """Find similar inscriptions in the corpus."""
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

    async def restore(
        self,
        text: str,
        language: Language = "greek",
        beam_width: int = DEFAULT_BEAM_WIDTH,
        temperature: float = 1.0,
        max_restoration_len: int = DEFAULT_MAX_RESTORATION_LEN,
        top_chars: Optional[int] = DEFAULT_TOP_CHARS,
        time_budget: Optional[float] = None,
    ) -> RestorationResult:
        """Async restore guarded by a non-blocking semaphore (429 on busy)."""
        if self._sem.locked():
            raise BusyError("An inference is already running; try again later.")
        async with self._sem:
            return await asyncio.to_thread(
                self.restore_sync,
                text,
                language,
                beam_width,
                temperature,
                max_restoration_len,
                top_chars,
                time_budget,
            )

    async def attribute(
        self, text: str, language: Language = "greek"
    ) -> AttributionResult:
        """Async attribute guarded by a non-blocking semaphore (429 on busy)."""
        if self._sem.locked():
            raise BusyError("An inference is already running; try again later.")
        async with self._sem:
            return await asyncio.to_thread(self.attribute_sync, text, language)

    async def contextualize(
        self, text: str, language: Language = "greek", top_k: int = 20
    ) -> ContextualizationResult:
        """Async contextualize guarded by a non-blocking semaphore (429 on busy)."""
        if self._sem.locked():
            raise BusyError("An inference is already running; try again later.")
        async with self._sem:
            return await asyncio.to_thread(
                self.contextualize_sync, text, language, top_k
            )


@lru_cache(maxsize=1)
def get_ithaca_service() -> IthacaService:
    """Get or create the Ithaca service singleton."""
    return IthacaService()


def initialize_all_models() -> dict[str, bool]:
    """Initialize both Greek and Latin models (blocking; use to_thread)."""
    service = get_ithaca_service()
    results: dict[str, bool] = {}

    logger.info("Initializing all Ithaca/Aeneas models...")

    # Try Greek
    results["greek"] = service.initialize_model("greek")

    # Try Latin
    results["latin"] = service.initialize_model("latin")

    logger.info(f"Model initialization complete: {results}")
    return results
