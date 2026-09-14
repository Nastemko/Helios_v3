"""Service facade tests for services.ithaca.service."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from services.ithaca.service import BusyError, IthacaService, _LoadedModel, _load_model


def _loaded_service() -> IthacaService:
    service = IthacaService()
    loaded = MagicMock()
    loaded.is_available = True
    loaded.region_map = {"names": []}
    service._models["greek"] = loaded
    return service


def _real_loaded_model(language: str = "greek") -> _LoadedModel:
    """A real _LoadedModel dict-entry (replaces the old IthacaModel mocks)."""
    return _LoadedModel(
        language=language,  # type: ignore[arg-type]
        forward=MagicMock(),
        params=None,
        alphabet=MagicMock(),
        region_map={},
        dataset={},
        retrieval={},
        vocab_char_size=35,
    )


def test_restore_declined_input_reports_available_false():
    service = _loaded_service()
    with patch(
        "services.ithaca.service.inference.restore",
        side_effect=ValueError("Input text too short."),
    ):
        result = service.restore_sync("εδοξεν ?", language="greek")
    assert result.available is False
    assert result.message == "Input text too short."


def test_out_of_alphabet_character_maps_to_friendly_message():
    service = _loaded_service()
    with patch(
        "services.ithaca.service.inference.restore",
        side_effect=KeyError("j"),
    ):
        result = service.restore_sync("imp caesar j?", language="greek")
    assert result.available is False
    assert "Unsupported character" in (result.message or "")


def test_busy_restore_raises_instead_of_queueing():
    """A second concurrent restore must fail fast (router maps to 429)."""

    async def _run() -> None:
        service = IthacaService()
        await service._sem.acquire()
        try:
            with pytest.raises(BusyError):
                await service.restore("εδοξεν τηι βουληι ????? αθηναιων")
        finally:
            service._sem.release()

    asyncio.run(_run())


class TestInitializeModelIdempotency(unittest.TestCase):
    """initialize_model must not reload a model that is already available."""

    def test_skips_reload_when_model_already_available(self):
        service = IthacaService()
        existing = _real_loaded_model("greek")
        service._models["greek"] = existing

        with patch("services.ithaca.service._load_model") as mock_load:
            result = service.initialize_model("greek")

        self.assertTrue(result)
        mock_load.assert_not_called()
        self.assertIs(service._models["greek"], existing)

    def test_reloads_when_cached_model_is_unavailable(self):
        service = IthacaService()
        stale = _LoadedModel(
            language="greek",
            forward=None,
            params=None,
            alphabet=MagicMock(),
            region_map={},
            dataset={},
            retrieval={},
            vocab_char_size=35,
        )
        service._models["greek"] = stale

        fresh = _real_loaded_model("greek")

        with patch(
            "services.ithaca.service._load_model", return_value=fresh
        ) as mock_load, patch("services.ithaca.service.Path.exists", return_value=True):
            result = service.initialize_model("greek")

        self.assertTrue(result)
        mock_load.assert_called_once()
        self.assertIs(service._models["greek"], fresh)

    def test_loads_when_no_model_cached(self):
        service = IthacaService()

        fresh = _real_loaded_model("latin")

        with patch(
            "services.ithaca.service._load_model", return_value=fresh
        ) as mock_load, patch("services.ithaca.service.Path.exists", return_value=True):
            result = service.initialize_model("latin")

        self.assertTrue(result)
        mock_load.assert_called_once()
        self.assertIs(service._models["latin"], fresh)


class TestInferenceFailuresAreReported(unittest.TestCase):
    """A declined input must not be reported as a successful analysis.

    The handlers used to return a result whose top_prediction equalled the
    input and whose available flag the router then hardcoded to True, so
    "text too short" and "no gaps" were indistinguishable from success.
    """

    def setUp(self):
        self.service = IthacaService()
        # A MagicMock rather than _LoadedModel: the service reads forward/params/
        # alphabet off the model before it ever calls into inference.
        loaded = MagicMock()
        loaded.is_available = True
        loaded.region_map = {"names": []}
        self.service._models["greek"] = loaded

    def test_restore_reports_the_reason_it_declined(self):
        with patch(
            "services.ithaca.service.inference.restore",
            side_effect=ValueError("Input text too short."),
        ):
            result = self.service.restore_sync("εδοξεν ?", language="greek")

        self.assertFalse(result.available)
        self.assertEqual(result.message, "Input text too short.")

    def test_attribute_reports_the_reason_it_declined(self):
        with patch(
            "services.ithaca.service.inference.attribute",
            side_effect=ValueError("Input text too short."),
        ):
            result = self.service.attribute_sync("εδοξεν", language="greek")

        self.assertFalse(result.available)
        self.assertEqual(result.message, "Input text too short.")

    def test_contextualize_reports_the_reason_it_declined(self):
        with patch(
            "services.ithaca.service.inference.contextualize",
            side_effect=ValueError("Input text too short."),
        ):
            result = self.service.contextualize_sync("εδοξεν", language="greek")

        self.assertFalse(result.available)
        self.assertEqual(result.message, "Input text too short.")

    def test_out_of_alphabet_character_does_not_escape_as_a_500(self):
        """The tokenizer raises KeyError, which used to be uncaught.

        Latin has no 'j'; neither alphabet has ',' or ';'.
        """
        with patch(
            "services.ithaca.service.inference.restore",
            side_effect=KeyError("j"),
        ):
            result = self.service.restore_sync("imp caesar j?", language="greek")

        self.assertFalse(result.available)
        self.assertIsNotNone(result.message)
        self.assertIn("Unsupported character", result.message or "")

    def test_successful_restoration_stays_available(self):
        """The failure plumbing must not flip the flag on a good result."""
        prediction = MagicMock()
        prediction.text = "εδοξεν"
        prediction.restored = [1]
        prediction.score = 0.9

        inference_result = MagicMock()
        inference_result.input_text = "εδοξ?ν"
        inference_result.top_prediction = "εδοξεν"
        inference_result.missing = [4]
        inference_result.predictions = [prediction]
        inference_result.prediction_saliency = []

        with patch(
            "services.ithaca.service.inference.restore",
            return_value=inference_result,
        ):
            result = self.service.restore_sync("εδοξ?ν", language="greek")

        self.assertTrue(result.available)
        self.assertIsNone(result.message)


class TestInitializeDoesNotSwallowExceptions(unittest.TestCase):
    """A failed load must surface as None, not as a half-built model."""

    def test_load_model_returns_none_on_failure(self):
        with patch("builtins.open", side_effect=OSError("boom")):
            result = _load_model(
                "greek",
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )

        self.assertIsNone(result)


class TestRestoreTimeBudgetFromSettings(unittest.TestCase):
    """restore_sync() must resolve its time budget from settings at call-time."""

    def _service_with_available_model(self) -> IthacaService:
        service = IthacaService()
        loaded = MagicMock()
        loaded.is_available = True
        service._models["greek"] = loaded
        return service

    def _inference_result(self) -> MagicMock:
        inference_result = MagicMock()
        inference_result.input_text = "εδοξ?ν"
        inference_result.top_prediction = "εδοξεν"
        inference_result.missing = []
        inference_result.predictions = []
        inference_result.prediction_saliency = []
        return inference_result

    def test_restore_uses_settings_time_budget_when_not_given(self):
        service = self._service_with_available_model()
        with patch(
            "services.ithaca.service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TIME_BUDGET", 1600.0):
            service.restore_sync("εδοξ?ν", language="greek")

        mock_restore.assert_called_once()
        self.assertEqual(mock_restore.call_args.kwargs["time_budget"], 1600.0)

    def test_restore_explicit_time_budget_passthrough(self):
        service = self._service_with_available_model()
        with patch(
            "services.ithaca.service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TIME_BUDGET", 1600.0):
            service.restore_sync("εδοξ?ν", language="greek", time_budget=10.0)

        mock_restore.assert_called_once()
        self.assertEqual(mock_restore.call_args.kwargs["time_budget"], 10.0)

    def test_explicit_none_resolves_to_settings(self):
        service = self._service_with_available_model()
        with patch(
            "services.ithaca.service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TIME_BUDGET", 1600.0):
            service.restore_sync("εδοξ?ν", language="greek", time_budget=None)

        mock_restore.assert_called_once()
        kwargs = mock_restore.call_args.kwargs
        self.assertEqual(kwargs["time_budget"], 1600.0)
