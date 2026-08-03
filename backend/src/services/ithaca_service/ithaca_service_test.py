import unittest
from unittest.mock import MagicMock, patch

from .ithaca_service import IthacaService


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


if __name__ == "__main__":
    unittest.main()
