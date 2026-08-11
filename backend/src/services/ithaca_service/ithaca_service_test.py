import unittest
from unittest.mock import MagicMock, patch

from .ithaca_service import IthacaModel, IthacaService


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


if __name__ == "__main__":
    unittest.main()
