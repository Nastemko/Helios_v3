"""Tests for the inscriptions API response contract.

Inscription.metadata_raw is a JSONB column, so SQLAlchemy hands the router a
dict. TextResponse previously declared it as a string, which Pydantic v2 will
not coerce — every detail request 500'd once the loader started populating the
column with residual PHI fields.
"""

import pytest
from pydantic import ValidationError

from routers.inscriptions import TextResponse


def _residual_metadata() -> dict:
    """Residual PHI metadata shaped like the real iphi.json leftovers."""
    return {
        "ids_alt": {"phi_id": 232883},
        "region_main_id": "1701",
        "partner_link": "https://example.org/phi/232883",
    }


def test_text_response_accepts_dict_metadata():
    """metadata_raw is a JSONB column, so the response model must accept a dict."""
    response = TextResponse(
        id=1,
        title="Dedication to Athena",
        text="μῆνιν ἄειδε θεά",
        metadata_raw=_residual_metadata(),
    )

    assert response.metadata_raw == _residual_metadata()


def test_text_response_preserves_nested_metadata():
    """Nested PHI structures survive serialization rather than being stringified."""
    response = TextResponse(
        id=1,
        title="Dedication to Athena",
        text="μῆνιν ἄειδε θεά",
        metadata_raw=_residual_metadata(),
    )

    dumped = response.model_dump()

    assert dumped["metadata_raw"]["ids_alt"] == {"phi_id": 232883}


def test_text_response_allows_null_metadata():
    """An inscription whose residual metadata is empty serializes as null."""
    response = TextResponse(
        id=1,
        title="Dedication to Athena",
        text="μῆνιν ἄειδε θεά",
        metadata_raw=None,
    )

    assert response.metadata_raw is None


def test_text_response_rejects_non_object_metadata():
    """A bare string is not valid residual metadata and must not be accepted."""
    with pytest.raises(ValidationError):
        TextResponse(
            id=1,
            title="Dedication to Athena",
            text="μῆνιν ἄειδε θεά",
            metadata_raw="not-an-object",
        )
