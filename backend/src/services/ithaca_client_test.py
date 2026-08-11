"""Tests for the Ithaca inference client.

The behaviour under test is degradation. Inference now lives behind a network
call to a service that scales to zero, so "not reachable right now" is an
ordinary condition, not an exception -- the inscription endpoints must keep
returning a well-formed body that says the model is unavailable, exactly as
they did when a checkpoint file was missing on disk.
"""

import unittest
from unittest.mock import patch

import httpx

from services.ithaca_client import IthacaClient


class _ClientTestCase(unittest.TestCase):
    """Shared setup: a client pointed at a URL nothing is listening on."""

    def setUp(self):
        with patch.dict(
            "os.environ", {"ITHACA_SERVICE_URL": "http://ithaca.invalid:8001"}
        ):
            self.client = IthacaClient()
        self.client._base_url = "http://ithaca.invalid:8001"


class TestUnreachableService(_ClientTestCase):
    """Every entry point degrades rather than raising."""

    def test_restore_degrades(self):
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            result = self.client.restore("εδοξεν τηι βουληι ????? και τωι δημωι")

        self.assertFalse(result.available)
        self.assertIsNotNone(result.message)
        # The router echoes top_prediction back to the UI; it must be the input
        # rather than an empty string, or the workbench blanks the user's text.
        self.assertEqual(result.top_prediction, "εδοξεν τηι βουληι ????? και τωι δημωι")
        self.assertEqual(result.predictions, [])

    def test_attribute_degrades_with_full_year_vector(self):
        """year_scores must stay 160 long even when nothing was computed.

        The frontend plots this array directly; a short one would break the
        date chart rather than showing it as empty.
        """
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            result = self.client.attribute("εδοξεν τηι βουληι")

        self.assertFalse(result.available)
        self.assertEqual(len(result.year_scores), 160)
        self.assertEqual(
            result.predicted_date_range, {"min": None, "max": None, "confidence": 0.0}
        )

    def test_contextualize_degrades(self):
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            result = self.client.contextualize("εδοξεν τηι βουληι")

        self.assertFalse(result.available)
        self.assertEqual(result.similar, [])

    def test_timeout_degrades_like_a_connection_error(self):
        """A cold start that overruns is the same story as a refused connection."""
        with patch("httpx.post", side_effect=httpx.ReadTimeout("too slow")):
            result = self.client.restore("εδοξεν τηι βουληι ?????")

        self.assertFalse(result.available)

    def test_status_reports_both_languages_unavailable(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            status = self.client.get_status()

        self.assertFalse(status["greek"]["available"])
        self.assertFalse(status["latin"]["available"])

    def test_is_available_is_false_when_unreachable(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            self.assertFalse(self.client.is_available("greek"))


class TestServiceErrors(_ClientTestCase):
    """Non-2xx and malformed bodies degrade too, rather than propagating."""

    def test_http_500_degrades(self):
        response = httpx.Response(
            500, request=httpx.Request("POST", "http://ithaca.invalid:8001/restore")
        )
        with patch("httpx.post", return_value=response):
            result = self.client.restore("εδοξεν τηι βουληι ?????")

        self.assertFalse(result.available)

    def test_503_model_not_loaded_degrades(self):
        """The service returns 503 when a language did not load on that instance."""
        response = httpx.Response(
            503, request=httpx.Request("POST", "http://ithaca.invalid:8001/restore")
        )
        with patch("httpx.post", return_value=response):
            result = self.client.restore("εδοξεν τηι βουληι ?????")

        self.assertFalse(result.available)

    def test_malformed_body_degrades(self):
        response = httpx.Response(
            200,
            content=b"not json",
            request=httpx.Request("POST", "http://ithaca.invalid:8001/restore"),
        )
        with patch("httpx.post", return_value=response):
            result = self.client.restore("εδοξεν τηι βουληι ?????")

        self.assertFalse(result.available)


class TestSuccessfulResponseMapping(_ClientTestCase):
    """A good response maps onto the dataclasses the routers already expect."""

    def test_restore_maps_all_fields(self):
        body = {
            "input_text": "abc ????? def",
            "top_prediction": "abc βουλη def",
            "missing_indices": [4, 5, 6, 7, 8],
            "predictions": [
                {
                    "text": "abc βουλη def",
                    "restored_indices": [4, 5, 6, 7, 8],
                    "score": 0.87,
                }
            ],
            "prediction_saliency": [{"text": "x", "restored_idx": 4, "saliency": 0.5}],
            "available": True,
            "message": None,
        }
        response = httpx.Response(
            200,
            json=body,
            request=httpx.Request("POST", "http://ithaca.invalid:8001/restore"),
        )
        with patch("httpx.post", return_value=response):
            result = self.client.restore("abc ????? def")

        self.assertTrue(result.available)
        self.assertEqual(result.top_prediction, "abc βουλη def")
        self.assertEqual(len(result.predictions), 1)
        self.assertEqual(result.predictions[0].score, 0.87)
        self.assertEqual(result.predictions[0].restored_indices, [4, 5, 6, 7, 8])
        self.assertEqual(result.prediction_saliency[0]["restored_idx"], 4)

    def test_attribute_carries_predicted_date_range_from_the_wire(self):
        """The date range is computed service-side and must survive transport.

        It used to be a @property on the dataclass. Recomputing it here would be
        a second implementation of the same rule, free to drift from the one the
        model service uses.
        """
        body = {
            "input_text": "abc",
            "locations": [{"location_id": 7, "name": "Athens", "score": 0.8}],
            "year_scores": [0.0] * 160,
            "predicted_date_range": {"min": -400, "max": -350, "confidence": 0.9},
            "date_saliency": [0.1],
            "location_saliency": [0.2],
            "available": True,
            "message": None,
        }
        response = httpx.Response(
            200,
            json=body,
            request=httpx.Request("POST", "http://ithaca.invalid:8001/attribute"),
        )
        with patch("httpx.post", return_value=response):
            result = self.client.attribute("abc")

        self.assertEqual(
            result.predicted_date_range, {"min": -400, "max": -350, "confidence": 0.9}
        )
        self.assertEqual(result.locations[0].name, "Athens")

    def test_declined_input_is_passed_through_not_overwritten(self):
        """available=False from the *model* must not be confused with a transport
        failure: the model's own message is the useful one and has to survive.
        """
        body = {
            "input_text": "abc",
            "top_prediction": "abc",
            "missing_indices": [],
            "predictions": [],
            "prediction_saliency": [],
            "available": False,
            "message": "Unsupported character for the greek model: 'j'.",
        }
        response = httpx.Response(
            200,
            json=body,
            request=httpx.Request("POST", "http://ithaca.invalid:8001/restore"),
        )
        with patch("httpx.post", return_value=response):
            result = self.client.restore("abc")

        self.assertFalse(result.available)
        self.assertIn("Unsupported character", result.message)


class TestAudience(_ClientTestCase):
    """The `aud` claim must be the bare service URL."""

    def test_audience_defaults_to_base_url(self):
        self.assertEqual(self.client._audience(), "http://ithaca.invalid:8001")

    def test_audience_has_no_path_component(self):
        """A path in the audience is the usual cause of a 401 that reads like a
        credentials failure but is an audience mismatch."""
        audience = self.client._audience()
        self.assertFalse(audience.rstrip("/").endswith("/restore"))
        self.assertEqual(audience.count("/"), 2)  # only the '//' in the scheme


if __name__ == "__main__":
    unittest.main()
