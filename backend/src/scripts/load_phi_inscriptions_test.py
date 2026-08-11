"""Tests for PHI inscription metadata extraction.

PHI records from iphi.json are flat — there is no nested "metadata" key — so
metadata_raw must be built from the fields that have no dedicated column.
"""

from scripts.load_phi_inscriptions import extract_residual_metadata


def _phi_record() -> dict:
    """A PHI record shaped like the real iphi.json entries."""
    return {
        "id": 12345,
        "text": "μῆνιν ἄειδε θεά",
        "region_main": "Attica (IG I-III)",
        "region_sub": "Athens: Agora",
        "date_str": "c. 450 BC",
        "date_min": -460,
        "date_max": -440,
        "date_circa": True,
        "partner_link": "https://example.org/phi/12345",
        "ids_alt": {"IG": "I3 1"},
    }


def test_residual_keeps_fields_without_columns():
    """partner_link and ids_alt have no column and must be preserved."""
    residual = extract_residual_metadata(_phi_record())

    assert residual is not None
    assert residual["partner_link"] == "https://example.org/phi/12345"
    assert residual["ids_alt"] == {"IG": "I3 1"}


def test_residual_omits_promoted_columns():
    """Fields with dedicated columns are not duplicated into the JSONB blob."""
    residual = extract_residual_metadata(_phi_record())

    assert residual is not None
    for promoted in (
        "id",
        "text",
        "region_main",
        "region_sub",
        "date_min",
        "date_max",
        "date_str",
        "date_circa",
    ):
        assert promoted not in residual


def test_residual_is_none_when_nothing_left_over():
    """A record with only promoted fields yields NULL rather than an empty dict."""
    record = {
        "id": 1,
        "text": "abc",
        "region_main": "Attica",
        "date_min": -400,
    }

    assert extract_residual_metadata(record) is None


def test_unknown_future_fields_are_retained():
    """Unmapped fields are captured rather than silently dropped."""
    record = _phi_record()
    record["some_new_phi_field"] = "keep me"

    residual = extract_residual_metadata(record)

    assert residual is not None
    assert residual["some_new_phi_field"] == "keep me"
