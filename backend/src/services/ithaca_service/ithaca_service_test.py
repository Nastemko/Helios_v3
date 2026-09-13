import unittest
from unittest.mock import MagicMock, patch

from config import settings

from .ithaca_service import IthacaModel, IthacaService
from .models import AttributionResult as ServiceAttribution


class _StubModel:
    """Stands in for IthacaModel; is_available is a property on the real class."""

    def __init__(self, available: bool = True):
        self.is_available = available


class TestInitializeModelIdempotency(unittest.TestCase):
    """initialize_model must not reload a model that is already available."""

    def test_skips_reload_when_model_already_available(self):
        service = IthacaService()
        existing = _StubModel(available=True)
        service._models["greek"] = existing

        with patch(
            "src.services.ithaca_service.ithaca_service.IthacaModel"
        ) as mock_model_cls:
            result = service.initialize_model("greek")

        self.assertTrue(result)
        mock_model_cls.assert_not_called()
        self.assertIs(service._models["greek"], existing)

    def test_reloads_when_cached_model_is_unavailable(self):
        service = IthacaService()
        service._models["greek"] = _StubModel(available=False)

        fresh = MagicMock()
        fresh.initialize.return_value = True

        with patch(
            "src.services.ithaca_service.ithaca_service.IthacaModel", return_value=fresh
        ) as mock_model_cls, patch(
            "src.services.ithaca_service.ithaca_service.Path.exists", return_value=True
        ):
            result = service.initialize_model("greek")

        self.assertTrue(result)
        mock_model_cls.assert_called_once_with("greek")
        self.assertIs(service._models["greek"], fresh)

    def test_loads_when_no_model_cached(self):
        service = IthacaService()

        fresh = MagicMock()
        fresh.initialize.return_value = True

        with patch(
            "src.services.ithaca_service.ithaca_service.IthacaModel", return_value=fresh
        ) as mock_model_cls, patch(
            "src.services.ithaca_service.ithaca_service.Path.exists", return_value=True
        ):
            result = service.initialize_model("latin")

        self.assertTrue(result)
        mock_model_cls.assert_called_once_with("latin")


class TestInferenceFailuresAreReported(unittest.TestCase):
    """A declined input must not be reported as a successful analysis.

    The handlers used to return a result whose top_prediction equalled the
    input and whose available flag the router then hardcoded to True, so
    "text too short" and "no gaps" were indistinguishable from success.
    """

    def setUp(self):
        self.service = IthacaService()
        # A MagicMock rather than _StubModel: the service reads forward/params/
        # alphabet off the model before it ever calls into inference.
        loaded = MagicMock()
        loaded.is_available = True
        loaded.region_map = {"names": []}
        self.service._models["greek"] = loaded

    def test_restore_reports_the_reason_it_declined(self):
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            side_effect=ValueError("Input text too short."),
        ):
            result = self.service.restore("εδοξεν ?", language="greek")

        self.assertFalse(result.available)
        self.assertEqual(result.message, "Input text too short.")

    def test_attribute_reports_the_reason_it_declined(self):
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.attribute",
            side_effect=ValueError("Input text too short."),
        ):
            result = self.service.attribute("εδοξεν", language="greek")

        self.assertFalse(result.available)
        self.assertEqual(result.message, "Input text too short.")

    def test_contextualize_reports_the_reason_it_declined(self):
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.contextualize",
            side_effect=ValueError("Input text too short."),
        ):
            result = self.service.contextualize("εδοξεν", language="greek")

        self.assertFalse(result.available)
        self.assertEqual(result.message, "Input text too short.")

    def test_out_of_alphabet_character_does_not_escape_as_a_500(self):
        """The vendored tokenizer raises KeyError, which used to be uncaught.

        Latin has no 'j'; neither alphabet has ',' or ';'.
        """
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            side_effect=KeyError("j"),
        ):
            result = self.service.restore("imp caesar j?", language="greek")

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
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=inference_result,
        ):
            result = self.service.restore("εδοξ?ν", language="greek")

        self.assertTrue(result.available)
        self.assertIsNone(result.message)


class TestInitializeDoesNotSwallowExceptions(unittest.TestCase):
    """`return` used to live inside a `finally`, hiding every error."""

    def test_initialize_returns_false_on_failure(self):
        model = IthacaModel("greek")

        with patch("builtins.open", side_effect=OSError("boom")):
            result = model.initialize(
                checkpoint_path=MagicMock(),
                dataset_path=MagicMock(),
                retrieval_path=MagicMock(),
            )

        self.assertFalse(result)
        self.assertFalse(model.initialized)


class TestInferenceConcurrencyGuard(unittest.TestCase):
    """A single restore saturates the CPUs; a second must be rejected."""

    def test_second_concurrent_acquire_fails_fast(self):
        service = IthacaService()

        self.assertTrue(service._inference_lock.acquire(blocking=False))
        try:
            self.assertFalse(
                service._inference_lock.acquire(blocking=False),
                "a second concurrent inference should not acquire the lock",
            )
        finally:
            service._inference_lock.release()

        # Released again, so a later request can proceed.
        self.assertTrue(service._inference_lock.acquire(blocking=False))
        service._inference_lock.release()


class TestRestoreTimeBudgetFromSettings(unittest.TestCase):
    """restore() must resolve its time budget from settings at call-time."""

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
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TIME_BUDGET", 1600.0):
            service.restore("εδοξ?ν", language="greek")

        mock_restore.assert_called_once()
        self.assertEqual(mock_restore.call_args.kwargs["time_budget"], 1600.0)

    def test_restore_explicit_time_budget_passthrough(self):
        service = self._service_with_available_model()
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TIME_BUDGET", 1600.0):
            service.restore("εδοξ?ν", language="greek", time_budget=10.0)

        mock_restore.assert_called_once()
        self.assertEqual(mock_restore.call_args.kwargs["time_budget"], 10.0)

    def test_explicit_none_resolves_to_settings(self):
        service = self._service_with_available_model()
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TIME_BUDGET", 1600.0):
            service.restore("εδοξ?ν", language="greek", time_budget=None)

        mock_restore.assert_called_once()
        kwargs = mock_restore.call_args.kwargs
        self.assertEqual(kwargs["time_budget"], 1600.0)


class TestRestoreKnobsFromSettings(unittest.TestCase):
    """restore()/contextualize() must resolve inference knobs from settings."""

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

    def test_restore_uses_settings_knobs_when_not_given(self):
        service = self._service_with_available_model()
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(
            settings.ithaca, "BEAM_WIDTH", 21
        ), patch.object(
            settings.ithaca, "DEFAULT_TEMPERATURE", 0.7
        ), patch.object(
            settings.ithaca, "DEFAULT_MAX_RESTORATION_LEN", 8
        ), patch.object(
            settings.ithaca, "TOP_CHARS", 4
        ):
            service.restore("εδοξ?ν", language="greek")

        mock_restore.assert_called_once()
        kwargs = mock_restore.call_args.kwargs
        self.assertEqual(kwargs["beam_width"], 21)
        self.assertEqual(kwargs["temperature"], 0.7)
        self.assertEqual(kwargs["unk_restoration_max_len"], 8)
        self.assertEqual(kwargs["top_chars"], 4)

    def test_restore_explicit_knobs_passthrough(self):
        service = self._service_with_available_model()
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(
            settings.ithaca, "BEAM_WIDTH", 21
        ), patch.object(
            settings.ithaca, "DEFAULT_TEMPERATURE", 0.7
        ):
            service.restore(
                "εδοξ?ν",
                language="greek",
                beam_width=10,
                temperature=0.5,
                max_restoration_len=5,
                top_chars=3,
            )

        mock_restore.assert_called_once()
        kwargs = mock_restore.call_args.kwargs
        self.assertEqual(kwargs["beam_width"], 10)
        self.assertEqual(kwargs["temperature"], 0.5)
        self.assertEqual(kwargs["unk_restoration_max_len"], 5)
        self.assertEqual(kwargs["top_chars"], 3)

    def test_restore_explicit_none_top_chars_stays_exhaustive(self):
        """None is meaningful for top_chars (exhaustive) and must not resolve."""
        service = self._service_with_available_model()
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(settings.ithaca, "TOP_CHARS", 4):
            service.restore("εδοξ?ν", language="greek", top_chars=None)

        mock_restore.assert_called_once()
        self.assertIsNone(mock_restore.call_args.kwargs["top_chars"])

    def test_restore_defaults_match_hardcoded(self):
        """Defaults preserve the previously hardcoded values."""
        service = self._service_with_available_model()
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.restore",
            return_value=self._inference_result(),
        ) as mock_restore, patch.object(
            settings.ithaca, "BEAM_WIDTH", 35
        ), patch.object(
            settings.ithaca, "DEFAULT_TEMPERATURE", 1.0
        ), patch.object(
            settings.ithaca, "DEFAULT_MAX_RESTORATION_LEN", 15
        ), patch.object(
            settings.ithaca, "TOP_CHARS", 8
        ):
            service.restore("εδοξ?ν", language="greek")

        kwargs = mock_restore.call_args.kwargs
        self.assertEqual(kwargs["beam_width"], 35)
        self.assertEqual(kwargs["temperature"], 1.0)
        self.assertEqual(kwargs["unk_restoration_max_len"], 15)
        self.assertEqual(kwargs["top_chars"], 8)

    def test_contextualize_uses_settings_top_k_when_not_given(self):
        service = self._service_with_available_model()
        inference_result = MagicMock()
        inference_result.ids = []
        inference_result.ids_alt = []
        inference_result.text = []
        inference_result.location_ids = []
        inference_result.date_min = []
        inference_result.date_max = []
        inference_result.score = []
        inference_result.partner_link = []
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.contextualize",
            return_value=inference_result,
        ) as mock_contextualize, patch.object(settings.ithaca, "CONTEXT_TOP_K", 7):
            service.contextualize("εδοξεν", language="greek")

        mock_contextualize.assert_called_once()
        self.assertEqual(mock_contextualize.call_args.kwargs["top_k"], 7)

    def test_contextualize_explicit_top_k_passthrough(self):
        service = self._service_with_available_model()
        inference_result = MagicMock()
        inference_result.ids = []
        inference_result.ids_alt = []
        inference_result.text = []
        inference_result.location_ids = []
        inference_result.date_min = []
        inference_result.date_max = []
        inference_result.score = []
        inference_result.partner_link = []
        with patch(
            "src.services.ithaca_service.ithaca_service.inference.contextualize",
            return_value=inference_result,
        ) as mock_contextualize, patch.object(settings.ithaca, "CONTEXT_TOP_K", 7):
            service.contextualize("εδοξεν", language="greek", top_k=3)

        mock_contextualize.assert_called_once()
        self.assertEqual(mock_contextualize.call_args.kwargs["top_k"], 3)

    def test_attribute_locations_kept_from_settings(self):
        """Only the first ATTRIBUTION_LOCATIONS_KEPT locations are returned."""
        service = self._service_with_available_model()
        loaded = service._models["greek"]
        loaded.region_map = {"names": []}

        locations = [MagicMock(location_id=i, score=1.0 / (i + 1)) for i in range(25)]
        inference_result = MagicMock()
        inference_result.input_text = "εδοξεν"
        inference_result.locations = locations
        inference_result.year_scores = [0.0] * 160
        inference_result.date_saliency = []
        inference_result.location_saliency = []

        with patch(
            "src.services.ithaca_service.ithaca_service.inference.attribute",
            return_value=inference_result,
        ), patch.object(settings.ithaca, "ATTRIBUTION_LOCATIONS_KEPT", 5):
            result: ServiceAttribution = service.attribute("εδοξεν", language="greek")

        self.assertEqual(len(result.locations), 5)

    def test_date_window_fraction_from_settings(self):
        """predicted_date_range threshold tracks DATE_WINDOW_FRACTION."""
        scores = [0.0] * 160
        scores[80] = 1.0
        scores[81] = 0.4
        result = ServiceAttribution(
            input_text="x",
            locations=[],
            year_scores=scores,
            date_saliency=[],
            location_saliency=[],
        )
        with patch.object(settings.ithaca, "DATE_WINDOW_FRACTION", 0.5):
            narrow = result.predicted_date_range
        with patch.object(settings.ithaca, "DATE_WINDOW_FRACTION", 0.25):
            wide = result.predicted_date_range

        # 0.4 clears a 0.25 window but not a 0.5 one.
        self.assertEqual(narrow["min"], narrow["max"])
        self.assertLess(wide["min"], wide["max"])


if __name__ == "__main__":
    unittest.main()
