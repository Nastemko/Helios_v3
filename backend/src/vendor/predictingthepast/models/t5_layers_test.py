"""Tests for the rotary-embedding table.

generate_fixed_pos_embedding is called once per attention call (6x per forward
pass) and rebuilds a ~3MB table at Precision.HIGHEST, which looks like an
obvious memoization target. It is NOT one: the function runs inside the jitted
forward pass, so an lru_cache stores tracers from the first trace and leaks them
into later calls. These tests pin that it stays uncached and correct.
"""

import unittest

import numpy as np

from vendor.predictingthepast.models.t5_layers import generate_fixed_pos_embedding


class TestRopeTable(unittest.TestCase):
    def test_is_not_memoized(self):
        """Caching this function breaks jit with UnexpectedTracerError.

        Regression guard: an lru_cache here caused every restore to fail once
        jax.jit was applied to the forward pass.
        """
        self.assertFalse(
            hasattr(generate_fixed_pos_embedding, "cache_info"),
            "generate_fixed_pos_embedding must not be lru_cached -- it is "
            "called inside jit and would leak tracers across calls",
        )

    def test_returns_correct_shapes(self):
        sin, cos = generate_fixed_pos_embedding(64, 128)
        self.assertEqual(np.asarray(sin).shape, (128, 64))
        self.assertEqual(np.asarray(cos).shape, (128, 64))

    def test_values_satisfy_trig_identity(self):
        sin, cos = generate_fixed_pos_embedding(64, 128)
        # sin^2 + cos^2 == 1 everywhere; catches a corrupted or truncated table.
        np.testing.assert_allclose(
            np.asarray(sin) ** 2 + np.asarray(cos) ** 2, 1.0, atol=1e-5
        )


if __name__ == "__main__":
    unittest.main()
