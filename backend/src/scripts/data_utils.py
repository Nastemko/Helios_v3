"""Utility functions for data validation and canonicalization in inscription loading."""

from typing import Optional


def canonicalize_region_name(region: Optional[str]) -> Optional[str]:
    """
    Canonicalize region names: trim whitespace, proper capitalization.

    Accepts None safely and returns None for non-string inputs.

    Args:
        region: Raw region name from data

    Returns:
        Canonicalized region name or None if invalid

    Examples:
        "  attica (ig i-iii)  " → "Attica (IG I-III)"
        "athens: agora" → "Athens: Agora"
        "" → None
        None → None
    """
    if not region or not isinstance(region, str):
        return None

    # Trim whitespace
    canonical = region.strip()

    if not canonical:
        return None

    # Convert to title case, but preserve certain patterns
    # Handle geographical and archaeological terms properly
    canonical = canonical.title()

    # Fix common capitalization issues
    # Preserve acronyms like "IG", "SEG", etc.
    acronyms = [
        "IG",
        "SEG",
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
    ]
    for acronym in acronyms:
        canonical = canonical.replace(f" {acronym.lower()} ", f" {acronym} ")
        canonical = canonical.replace(f"({acronym.lower()})", f"({acronym})")

    return canonical if canonical else None


def parse_date_value(date_val: Optional[object]) -> Optional[int]:
    """
    Parse date value with None fallback for invalid values.

    Accepts None and other non-string inputs gracefully.

    Args:
        date_val: Raw date value (string, number, etc.)

    Returns:
        Integer date value or None if invalid

    Examples:
        "-350" → -350 (350 BC)
        "100" → 100 (100 AD)
        None → None
        "invalid" → None
    """
    if date_val is None:
        return None

    try:
        # Handle string numbers (including negative for BC)
        return int(str(date_val).strip())
    except (ValueError, TypeError):
        return None


def validate_inscription_data(inscription: dict) -> dict:
    """
    Validate and canonicalize inscription data for loading.

    Args:
        inscription: Raw inscription data dictionary

    Returns:
        Dictionary with validated and canonicalized data
    """
    return {
        "region_main": canonicalize_region_name(inscription.get("region_main")),
        "region_sub": canonicalize_region_name(inscription.get("region_sub")),
        "date_min": parse_date_value(inscription.get("date_min")),
        "date_max": parse_date_value(inscription.get("date_max")),
    }


def prepare_metadata_for_jsonb(inscription: dict, phi_id: str) -> dict:
    """
    Prepare metadata for JSONB storage, excluding extracted fields.

    Args:
        inscription: Raw inscription data
        phi_id: PHI identifier

    Returns:
        Dictionary with metadata for JSONB column
    """
    return {
        "phi_id": phi_id,
        "source": "Packard Humanities Institute",
        "date_str": inscription.get("date_str"),
        "date_circa": inscription.get("date_circa"),
        "region_main_id": inscription.get("region_main_id"),
        "region_sub_id": inscription.get("region_sub_id"),
        "metadata_raw": inscription.get("metadata"),
        # Don't duplicate extracted fields in JSONB
    }
