"""Async load driver for the ``/publications`` endpoint.

The driver is closed-loop: a fixed number of workers each hold at most one
request in flight and issue the next as soon as the previous completes. That is
the right model for the question CCWG#15 asks -- "how many concurrent users can
this serve inside the latency budget" -- and it cannot drive the service into an
unbounded queue the way an open-loop arrival rate can, which would report queue
delay as service latency.

Two measurement details matter more than they look:

* All workers share one ``AsyncClient`` with a keep-alive pool sized to the
  concurrency, so a TLS handshake is not charged to individual requests.
* Every stage runs a discarded warmup first. Without it the first samples of a
  run carry connection setup and whatever the server had cold, which at the
  sample counts a benchmark like this uses is enough to move the p90 on its own.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

from benchmarks.publications.metrics import Sample, StageReport
from benchmarks.publications.workload import RunPlan, Workload

# Seeds for per-worker corpora are derived from the plan seed by offset, so a
# seeded run is reproducible without every worker drawing the same identifiers.
_WORKER_SEED_STRIDE = 1_000_003
# Let in-flight work drain between ramp stages so one stage's queue does not
# land in the next stage's latencies.
_STAGE_COOLDOWN_SECONDS = 1.0


class _Budget:
    """A shared countdown of requests still to be issued.

    Safe under asyncio because ``claim`` never awaits between reading and
    decrementing, so no other task can interleave.
    """

    def __init__(self, total: int):
        self.remaining = total

    def claim(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


@dataclass
class RunResult:
    """Every stage of one benchmark run, plus how it was configured."""

    plan: RunPlan
    stages: List[StageReport] = field(default_factory=list)
    request_id_mismatches: int = 0

    @property
    def all_samples(self) -> List[Sample]:
        return [sample for stage in self.stages for sample in stage.samples]


def _parse_response(response: httpx.Response, expected_request_id: str) -> Dict[str, object]:
    """Pull the metrics the benchmark needs out of one response body.

    A 200 whose body cannot be read as the documented shape is treated as a
    parse error rather than a success, because a benchmark that scored a
    malformed 200 as a fast request would hide exactly the failure mode a load
    test exists to find.
    """
    parsed: Dict[str, object] = {
        "server_ms": None,
        "found": 0,
        "not_found": 0,
        "request_id_matched": True,
        "error": None,
    }
    if response.status_code != 200:
        return parsed
    try:
        body = response.json()
        meta = body["_meta"]
        parsed["server_ms"] = int(meta["processing_time_ms"])
        parsed["found"] = len(body["results"])
        parsed["not_found"] = len(body["not_found"])
        parsed["request_id_matched"] = meta.get("request_id") == expected_request_id
    except (ValueError, KeyError, TypeError) as error:
        parsed["error"] = f"malformed-response:{type(error).__name__}"
    return parsed


async def _issue_request(
    client: httpx.AsyncClient,
    workload: Workload,
    identifiers: List[str],
) -> Tuple[Sample, bool]:
    """Issue one request and time it end to end, including reading the body."""
    request_id = str(uuid.uuid4())
    path, kwargs = workload.build_request(identifiers, request_id)

    started_at = time.perf_counter()
    try:
        response = await client.request(workload.normalized_method, path, **kwargs)
    except httpx.HTTPError as error:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return (
            Sample(
                client_ms=elapsed_ms,
                requested=len(identifiers),
                error=f"{type(error).__name__}",
            ),
            True,
        )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0

    parsed = _parse_response(response, request_id)
    sample = Sample(
        client_ms=elapsed_ms,
        status=response.status_code,
        server_ms=parsed["server_ms"],
        requested=len(identifiers),
        found=parsed["found"],
        not_found=parsed["not_found"],
        response_bytes=len(response.content),
        error=parsed["error"],
    )
    return sample, bool(parsed["request_id_matched"])


async def _worker(
    client: httpx.AsyncClient,
    workload: Workload,
    budget: _Budget,
    seed: Optional[int],
    collected: List[Sample],
    mismatches: List[int],
) -> None:
    corpus = workload.build_corpus(seed)
    while budget.claim():
        sample, request_id_matched = await _issue_request(client, workload, workload.next_batch(corpus))
        collected.append(sample)
        if not request_id_matched:
            mismatches.append(1)


async def _run_stage(
    client: httpx.AsyncClient,
    plan: RunPlan,
    concurrency: int,
    total_requests: int,
    seed_offset: int,
) -> Tuple[List[Sample], float, int]:
    budget = _Budget(total_requests)
    collected: List[Sample] = []
    mismatches: List[int] = []
    base_seed = None if plan.seed is None else plan.seed + seed_offset

    started_at = time.perf_counter()
    await asyncio.gather(
        *(
            _worker(
                client,
                plan.workload,
                budget,
                None if base_seed is None else base_seed + index * _WORKER_SEED_STRIDE,
                collected,
                mismatches,
            )
            for index in range(concurrency)
        )
    )
    return collected, time.perf_counter() - started_at, len(mismatches)


async def run_plan(plan: RunPlan, cache_primed: bool = False) -> RunResult:
    """Execute every stage of ``plan`` and return the collected samples."""
    result = RunResult(plan=plan)
    peak_concurrency = max(plan.stages)
    limits = httpx.Limits(
        max_connections=peak_concurrency,
        max_keepalive_connections=peak_concurrency,
    )

    async with httpx.AsyncClient(
        base_url=plan.normalized_base_url,
        timeout=plan.timeout_seconds,
        limits=limits,
        headers={"Accept": "application/json"},
    ) as client:
        for stage_index, concurrency in enumerate(plan.stages):
            if stage_index:
                await asyncio.sleep(_STAGE_COOLDOWN_SECONDS)

            if plan.warmup_requests:
                # A negative seed offset keeps the warmup drawing identifiers
                # that the measured stage will not ask for again. Warming the
                # connection pool is the point; warming the backend cache for
                # the very identifiers under measurement is not.
                await _run_stage(
                    client,
                    plan,
                    concurrency=min(concurrency, plan.warmup_requests),
                    total_requests=plan.warmup_requests,
                    seed_offset=-(stage_index + 1),
                )

            samples, wall_seconds, mismatches = await _run_stage(
                client,
                plan,
                concurrency=concurrency,
                total_requests=plan.requests,
                seed_offset=stage_index,
            )
            result.request_id_mismatches += mismatches
            result.stages.append(
                StageReport(
                    label=f"c={concurrency}",
                    concurrency=concurrency,
                    wall_seconds=wall_seconds,
                    samples=samples,
                    cache_primed=cache_primed,
                )
            )
    return result


async def verify_pmid_pool(base_url: str, candidates: List[str], timeout_seconds: float = 30.0) -> List[str]:
    """Return the subset of ``candidates`` the deployment can actually resolve.

    Calling this primes the backend cache for every identifier it confirms, so a
    run measured against a verified pool reports warm-cache latency. Runs that
    use it are labelled ``cache_primed`` for that reason.
    """
    resolved: List[str] = []
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds) as client:
        for start in range(0, len(candidates), 100):
            chunk = candidates[start : start + 100]
            response = await client.post("/publications", json={"ids": chunk, "request_id": "corpus-verify"})
            response.raise_for_status()
            resolved.extend(response.json()["results"].keys())
    return resolved
