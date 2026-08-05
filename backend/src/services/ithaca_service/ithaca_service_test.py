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


class TestForwardIsJitted(unittest.TestCase):
    """The forward pass must be compiled, not raw eager model.apply."""

    def test_make_forward_returns_jitted_callable(self):
        model = IthacaModel("greek")

        class _FakeFlaxModule:
            """Minimal stand-in; jax.jit only needs something callable."""

            def apply(self, params, text_char=None, **kwargs):
                return None, None, text_char, None, text_char

        jitted = model._make_forward(_FakeFlaxModule())

        self.assertTrue(
            hasattr(jitted, "_cache_size"),
            "forward is not a jax.jit-wrapped callable",
        )


class TestInitializeDoesNotSwallowExceptions(unittest.TestCase):
    """`return` used to live in a `finally`, hiding every error."""

    def test_initialize_returns_false_and_logs_on_failure(self):
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
