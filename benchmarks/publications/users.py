"""A user-population model for the ``/publications`` benchmark.

The closed-loop driver in :mod:`benchmarks.publications.runner` answers "what is
the capacity ceiling", and it answers it by keeping N requests in flight at all
times. That is deliberately not a model of N people: a closed-loop worker issues
its next request the instant the previous one returns, so it behaves like an
infinitely impatient robot rather than a reader. Concurrency and users are
related, but by a factor that is easy to be off by two orders of magnitude on.

Little's Law is the bridge. For a population in steady state::

    users = throughput x (service latency + think time)

A reader who spends 30 s looking at a result page before triggering another
lookup occupies the service for roughly 90 ms of those 30 s, so one such user
offers about 0.033 requests per second, not the ~11 per second a saturated
closed-loop worker offers. The same measured throughput therefore supports
hundreds or thousands of users while supporting only a handful of closed-loop
workers, and neither number is wrong -- they answer different questions.

This module models the population directly: N virtual users, each issuing a
request, waiting an exponentially distributed think time, and issuing another.
Two details make it a population rather than N copies of one user:

* Think times are exponential, not fixed. A fixed gap would keep users locked in
  lockstep with whatever phase they started in, producing periodic bursts that a
  real independent population does not have.
* Users share one popularity-ranked catalogue, so their requests overlap the way
  real readers' interests overlap. That overlap is what a backend cache actually
  gets to absorb, and it is invisible to a model where every user draws
  independently at random.
"""

import asyncio
import random
import time
from dataclasses import dataclass, replace
from typing import Dict, List, Optional

import httpx

from benchmarks.publications.corpus import CorpusConfig, IdentifierCorpus
from benchmarks.publications.metrics import Sample, StageReport
from benchmarks.publications.runner import RunResult, _issue_request
from benchmarks.publications.workload import RunPlan

# A catalogue much larger than one request keeps the long tail genuinely cold. If
# the catalogue were only a few batches wide, every paper would be cached within
# seconds and the run would measure the warm path exclusively.
DEFAULT_CATALOG_SIZE = 50_000
# Classic Zipf. Publication access is heavily skewed, and this is the usual
# first-order model for it.
DEFAULT_ZIPF_EXPONENT = 1.0
# Below this many think times of run length, the joining-request transient still
# inflates the observed rate by more than ~5% and the offered-versus-achieved
# reading should not be trusted.
MIN_STEADY_STATE_THINK_TIMES = 10.0


@dataclass(frozen=True)
class UserModel:
    """A population of readers, described the way capacity planning describes one."""

    users: int
    # Mean seconds a user spends before its next request. This is the assumption
    # the whole user-count answer rests on, so it is explicit and reported.
    think_time_seconds: float
    duration_seconds: float
    catalog_size: int = DEFAULT_CATALOG_SIZE
    zipf_exponent: float = DEFAULT_ZIPF_EXPONENT

    def __post_init__(self) -> None:
        if self.users < 1:
            raise ValueError("users must be >= 1")
        if self.think_time_seconds <= 0:
            raise ValueError("think_time_seconds must be greater than zero")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")
        if self.catalog_size < 1:
            raise ValueError("catalog_size must be >= 1")
        if self.zipf_exponent < 0:
            raise ValueError("zipf_exponent must be >= 0")

    @property
    def offered_rate_rps(self) -> float:
        """Requests per second the population intends to offer.

        This ignores service latency, so it slightly overstates the offered rate
        when latency is a meaningful fraction of the think time. The achieved
        rate is measured rather than derived, and the gap between the two is what
        says whether the service kept up.
        """
        return self.users / self.think_time_seconds

    @property
    def think_times_elapsed(self) -> float:
        """Run length measured in think times, which sets the startup bias.

        Every user issues one request the moment it joins and then settles into
        its think-time cadence, so a short run is dominated by those joining
        requests. Over ``duration = k * think_time`` the observed rate runs
        roughly ``1 + 1/(2k)`` times the steady-state rate: 25% high at k=2, 5%
        at k=10, 1% at k=60. The latency samples are unaffected -- each is an
        independent per-request measurement -- but the offered-versus-achieved
        comparison is only meaningful once k is large.
        """
        return self.duration_seconds / self.think_time_seconds

    @property
    def reaches_steady_state(self) -> bool:
        """Whether the run is long enough for the rate comparison to mean anything."""
        return self.think_times_elapsed >= MIN_STEADY_STATE_THINK_TIMES

    def describe(self) -> str:
        return (
            f"{self.users} users, {self.think_time_seconds:g}s mean think time "
            f"({self.offered_rate_rps:.1f} rps offered), "
            f"{self.catalog_size} paper catalogue at zipf {self.zipf_exponent:g}"
        )


def supported_users(throughput_rps: float, latency_ms: float, think_time_seconds: float) -> float:
    """Users a measured throughput supports, by Little's Law.

    ``latency_ms`` is included rather than dropped because at short think times
    it stops being negligible: at a 1 s think time a 90 ms service latency is
    most of a 10% correction.
    """
    if throughput_rps <= 0 or think_time_seconds <= 0:
        return 0.0
    return throughput_rps * (latency_ms / 1000.0 + think_time_seconds)


def capacity_table(
    throughput_rps: float,
    latency_ms: float,
    think_times: Optional[List[float]] = None,
) -> List[Dict[str, float]]:
    """Translate one measured throughput into user counts across think times.

    The think time is an assumption about reader behaviour rather than something
    the benchmark can measure, so the honest presentation is a sensitivity range
    instead of a single figure.
    """
    think_times = think_times or [5.0, 10.0, 30.0, 60.0, 120.0]
    return [
        {
            "think_time_seconds": think_time,
            "requests_per_user_rps": round(1.0 / (latency_ms / 1000.0 + think_time), 4),
            "supported_users": round(supported_users(throughput_rps, latency_ms, think_time)),
        }
        for think_time in think_times
    ]


async def _virtual_user(
    client: httpx.AsyncClient,
    plan: RunPlan,
    corpus: IdentifierCorpus,
    model: UserModel,
    generator: random.Random,
    deadline: float,
    collected: List[Sample],
    request_id_mismatches: List[int],
) -> None:
    """One reader: request, think, repeat, until the run's deadline."""
    # Stagger arrivals across the first think-time window. Without this every
    # user fires at t=0, which measures a synchronized thundering herd before the
    # exponential think times have had time to disperse them.
    await asyncio.sleep(generator.uniform(0.0, model.think_time_seconds))

    while time.monotonic() < deadline:
        identifiers = corpus.catalog_batch(plan.workload.batch_size)
        sample, request_id_matched = await _issue_request(client, plan.workload, identifiers)
        collected.append(sample)
        if not request_id_matched:
            request_id_mismatches.append(1)

        # Exponential rather than fixed: the memoryless gap is what keeps
        # independent users from drifting into lockstep.
        think = generator.expovariate(1.0 / model.think_time_seconds)
        if time.monotonic() + think >= deadline:
            return
        await asyncio.sleep(think)


async def run_user_plan(plan: RunPlan, model: UserModel) -> RunResult:
    """Run a simulated user population against the deployment.

    Unlike the closed-loop driver, all users share one corpus. That is the point:
    a shared catalogue is what produces overlapping requests between users. The
    corpus is safe to share because drawing a batch never awaits, so no two tasks
    can interleave inside a draw.
    """
    corpus = IdentifierCorpus(
        CorpusConfig(seed=plan.seed),
        identifier_pool=plan.workload.identifier_pool,
    )
    if plan.workload.uses_identifier_pool:
        corpus.seed_catalog_from_identifiers(plan.workload.identifier_pool, model.zipf_exponent)
        # The entire curated pool is the shared catalogue; reflect that actual
        # input in the population report instead of repeating --catalog-size,
        # which only controls synthesized catalogues.
        model = replace(model, catalog_size=len(plan.workload.identifier_pool))
    else:
        corpus.seed_catalog(model.catalog_size, model.zipf_exponent)
    generator = random.Random(plan.seed)

    collected: List[Sample] = []
    request_id_mismatches: List[int] = []
    # Connections are pooled per user, since a user population really does hold
    # that many sockets open against the service.
    limits = httpx.Limits(max_connections=model.users, max_keepalive_connections=model.users)

    async with httpx.AsyncClient(
        base_url=plan.normalized_base_url,
        timeout=plan.timeout_seconds,
        limits=limits,
        headers={"Accept": "application/json"},
    ) as client:
        started_at = time.perf_counter()
        deadline = time.monotonic() + model.duration_seconds
        await asyncio.gather(
            *(
                _virtual_user(
                    client,
                    plan,
                    corpus,
                    model,
                    generator,
                    deadline,
                    collected,
                    request_id_mismatches,
                )
                for _ in range(model.users)
            )
        )
        wall_seconds = time.perf_counter() - started_at

    result = RunResult(plan=plan, user_model=model)
    result.request_id_mismatches = len(request_id_mismatches)
    result.stages.append(
        StageReport(
            label=f"{model.users}u",
            concurrency=model.users,
            wall_seconds=wall_seconds,
            samples=collected,
        )
    )
    return result
