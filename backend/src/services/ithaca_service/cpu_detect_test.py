"""Effective CPU detection under container CPU quotas.

The deployed shard worker runs with `NanoCpus=3e9` on a 4-core box, where
both `os.cpu_count()` and `os.sched_getaffinity` report 4 and only the
cgroup quota reports the true limit of 3. Overcounting there would
oversubscribe the most constrained node in the cluster, so each source is
pinned individually.
"""

from unittest.mock import mock_open, patch

from services.ithaca_service.cpu_detect import effective_cpu_count


class TestEffectiveCpuCount:
    """Quota, affinity, and the interaction between them."""

    def test_quota_below_affinity_wins(self):
        """The deployed worker: 4 visible cores, quota of 3."""
        with patch("os.sched_getaffinity", return_value=set(range(4))), patch(
            "builtins.open", mock_open(read_data="300000 100000")
        ):
            assert effective_cpu_count() == 3

    def test_unlimited_quota_falls_back_to_affinity(self):
        """The deployed coordinator: `cpu.max` reads 'max'."""
        with patch("os.sched_getaffinity", return_value=set(range(6))), patch(
            "builtins.open", mock_open(read_data="max 100000")
        ):
            assert effective_cpu_count() == 6

    def test_missing_cgroup_file_falls_back_to_affinity(self):
        """Bare-metal and macOS have no cgroup v2 file at all."""
        with patch("os.sched_getaffinity", return_value=set(range(8))), patch(
            "builtins.open", side_effect=FileNotFoundError
        ):
            assert effective_cpu_count() == 8

    def test_unreadable_cgroup_file_falls_back_to_affinity(self):
        """A malformed or permission-denied quota must not crash startup."""
        with patch("os.sched_getaffinity", return_value=set(range(2))), patch(
            "builtins.open", mock_open(read_data="garbage")
        ):
            assert effective_cpu_count() == 2

    def test_affinity_below_quota_wins(self):
        """Taskset-pinned to 2 cores with a generous quota."""
        with patch("os.sched_getaffinity", return_value={0, 1}), patch(
            "builtins.open", mock_open(read_data="800000 100000")
        ):
            assert effective_cpu_count() == 2

    def test_fractional_quota_rounds_down(self):
        """A 2.5-core quota supports 2 fully-busy threads, not 3."""
        with patch("os.sched_getaffinity", return_value=set(range(4))), patch(
            "builtins.open", mock_open(read_data="250000 100000")
        ):
            assert effective_cpu_count() == 2

    def test_never_returns_below_one(self):
        """A sub-core quota must still allow one thread to run."""
        with patch("os.sched_getaffinity", return_value={0}), patch(
            "builtins.open", mock_open(read_data="50000 100000")
        ):
            assert effective_cpu_count() == 1
