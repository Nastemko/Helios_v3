"""Text helpers used by the Ithaca inference path."""

import re
import unicodedata

import numpy as np


def strip_accents(s: str) -> str:
    """Strip combining marks (accents) from a string."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def text_to_idx(t: str, alphabet) -> np.ndarray:
    """Convert a string to character indices."""
    return np.array([alphabet.char2idx[c] for c in t], dtype=np.int32)
