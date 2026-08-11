"""How many CPUs this process may actually use.

`os.cpu_count()` reports the host's cores and ignores container limits
entirely. On the deployed shard worker -- a 4-core box run with
`NanoCpus=3e9` -- both it and `os.sched_getaffinity` report 4 while the real
allowance is 3. Sizing a thread pool from either would oversubscribe the most
constrained node in the cluster by a third.

The cgroup v2 quota is the only source that gets that case right, so it is
read directly and combined with the affinity mask: a process can be limited
by either, and the binding constraint is whichever is smaller.
"""

import logging
import os

logger = logging.getLogger(__name__)

CGROUP_V2_CPU_MAX = "/sys/fs/cgroup/cpu.max"


def _quota_cpus() -> int | None:
    """CPUs allowed by the cgroup v2 quota, or None if unlimited/unreadable.

    The file holds "<quota> <period>", where quota is the literal string
    "max" when no limit is set. Rounded down: a 2.5-core allowance cannot
    keep 3 threads busy, and overshooting costs more than undershooting.

    Every failure mode -- absent file (bare metal, macOS, cgroup v1),
    unreadable, malformed -- returns None so the caller falls back rather
    than raising. This runs during model init, where a crash would take out
    the whole service for a tuning hint.
    """
    try:
        with open(CGROUP_V2_CPU_MAX) as handle:
            quota_raw, period_raw = handle.read().split()
        if quota_raw == "max":
            return None
        return max(1, int(float(quota_raw) / float(period_raw)))
    except (OSError, ValueError):
        return None


def effective_cpu_count() -> int:
    """Usable CPU count, honouring both container quota and affinity mask.

    Never returns below 1, so callers can divide by it unguarded.
    """
    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:  # not available on every platform
        affinity = os.cpu_count() or 1

    quota = _quota_cpus()
    if quota is None:
        return max(1, affinity)
    return max(1, min(quota, affinity))
