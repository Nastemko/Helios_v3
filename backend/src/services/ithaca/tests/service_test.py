"""Service facade tests (moved + extended from ithaca_service_test.py)."""

from unittest.mock import MagicMock, patch

import pytest

from services.ithaca.service import IthacaService


def _loaded_service() -> IthacaService:
    service = IthacaService()
    loaded = MagicMock()
    loaded.is_available = True
    loaded.region_map = {"names": []}
    service._models["greek"] = loaded
    return service


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
    import asyncio

    from services.ithaca.service import BusyError

    async def _run() -> None:
        service = IthacaService()
        await service._sem.acquire()
        try:
            with pytest.raises(BusyError):
                await service.restore("εδοξεν τηι βουληι ????? αθηναιων")
        finally:
            service._sem.release()

    asyncio.run(_run())
