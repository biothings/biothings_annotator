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
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import httpx

from benchmarks.publications.metrics import Sample, StageReport
from benchmarks.publications.workload import (
    DEFAULT_COMPARISON_STRATEGIES,
    LOOKUP_STRATEGY_HEADER,
    SUPPORTED_LOOKUP_STRATEGIES,
    RunPlan,
    Workload,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    # users imports _issue_request from here, so the annotation is deferred.
    from benchmarks.publications.users import UserModel

# Seeds for per-worker corpora are derived from the plan seed by offset, so a
# seeded run is reproducible without every worker drawing the same identifiers.
_WORKER_SEED_STRIDE = 1_000_003
# Let in-flight work drain between ramp stages so one stage's queue does not
# land in the next stage's latencies.
_STAGE_COOLDOWN_SECONDS = 1.0


def _exercises_changed_path(identifiers: Tuple[str, ...], strategies: Tuple[str, str]) -> bool:
    """Whether this batch reaches code that differs between the selected arms.

    The selector implementations deliberately overlap: current and bulk-search
    differ only for alternative IDs; bulk-search and combined-search differ
    when a PMID is present; current and combined-search differ for every
    nonempty normal-path request. A non-ASCII alternative makes every strategy
    use the exact fallback. The classification is independent of arm order.
    """
    strategy_set = frozenset(strategies)
    search_ids = tuple(identifier for identifier in identifiers if not identifier.lower().startswith("pmid:"))
    # A single non-ASCII alternative identifier makes every implementation use
    # the current exact-search fallback for the whole request. Classifying a
    # mixed batch by its PMID or ASCII alternatives in that case would claim a
    # treatment difference that the service deliberately did not execute.
    if any(not identifier.isascii() for identifier in search_ids):
        return False

    has_pmid = len(search_ids) < len(identifiers)
    has_alternative = any(identifier.lower().startswith(("doi:", "pmc:")) for identifier in identifiers)
    if strategy_set == frozenset(("current", "bulk-search")):
        return has_alternative
    if strategy_set == frozenset(("bulk-search", "combined-search")):
        return has_pmid
    if strategy_set == frozenset(("current", "combined-search")):
        return bool(identifiers)
    return False


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
    lookup_strategy_mismatches: int = 0
    # Set when the run modelled a user population rather than a fixed number of
    # requests in flight. It changes how the result should be read, so the
    # report needs to know.
    user_model: Optional["UserModel"] = None

    @property
    def all_samples(self) -> List[Sample]:
        return [sample for stage in self.stages for sample in stage.samples]


@dataclass(frozen=True)
class PairedObservation:
    """Both selected lookup treatments applied to one identical batch."""

    index: int
    first_strategy: str
    identifiers: Tuple[str, ...]
    samples: Dict[str, Sample]
    strategies: Tuple[str, str] = DEFAULT_COMPARISON_STRATEGIES
    request_id_mismatches: int = 0
    lookup_strategy_mismatches: int = 0
    semantic_match: Optional[bool] = None

    def __post_init__(self) -> None:
        if len(self.strategies) != 2 or self.strategies[0] == self.strategies[1]:
            raise ValueError("paired observations require two distinct strategies")
        if self.first_strategy not in self.strategies:
            raise ValueError("first_strategy must be one of the paired strategies")
        if set(self.samples) != set(self.strategies):
            raise ValueError("samples must contain exactly the paired strategies")

    def sample_for(self, strategy: str) -> Sample:
        if strategy not in self.strategies:
            raise ValueError(f"strategy {strategy!r} is not part of this pair")
        return self.samples[strategy]

    # These properties preserve the small Python API used by existing
    # current-vs-bulk callers while the generic mapping supports any pair.
    @property
    def current(self) -> Sample:
        return self.sample_for("current")

    @property
    def bulk_search(self) -> Sample:
        return self.sample_for("bulk-search")

    @property
    def order_label(self) -> str:
        return f"{self.first_strategy}-first"

    @property
    def alternative_identifier_count(self) -> int:
        return sum(identifier.lower().startswith(("doi:", "pmc:")) for identifier in self.identifiers)

    @property
    def exercises_changed_path(self) -> bool:
        return _exercises_changed_path(self.identifiers, self.strategies)

    @staticmethod
    def _unresolved_for(sample: Sample) -> int:
        # Only a parsed response can establish a miss. Transport and malformed
        # responses are already invalid for their own reason and must not be
        # misreported as a batch of confirmed not_found identifiers.
        if sample.status != 200 or sample.semantic_signature is None:
            return 0
        return max(sample.not_found, sample.requested - sample.found, 0)

    @property
    def unresolved_identifier_count(self) -> int:
        # Both arms receive the same batch and semantic equality is checked
        # separately. Count unresolved identifiers once per pair, not once per
        # treatment.
        return max(self._unresolved_for(self.sample_for(strategy)) for strategy in self.strategies)

    @property
    def fully_resolved(self) -> bool:
        return self.unresolved_identifier_count == 0

    @property
    def valid(self) -> bool:
        """Whether this pair can support a like-for-like latency delta."""
        return (
            all(self.sample_for(strategy).ok for strategy in self.strategies)
            and all(self.sample_for(strategy).lookup_fallback is False for strategy in self.strategies)
            and not self.request_id_mismatches
            and not self.lookup_strategy_mismatches
            and self.semantic_match is True
            and self.fully_resolved
        )

    @property
    def lookup_fallback_samples(self) -> int:
        return sum(
            self.sample_for(strategy).status == 200 and self.sample_for(strategy).lookup_fallback is True
            for strategy in self.strategies
        )

    @property
    def lookup_fallback_attribution_missing(self) -> int:
        return sum(
            self.sample_for(strategy).status == 200 and self.sample_for(strategy).lookup_fallback is None
            for strategy in self.strategies
        )


@dataclass
class ComparisonStage:
    """One concurrency stage from a paired lookup-strategy comparison."""

    label: str
    concurrency: int
    wall_seconds: float
    strategies: Tuple[str, str] = DEFAULT_COMPARISON_STRATEGIES
    pairs: List[PairedObservation] = field(default_factory=list)
    cache_primed: bool = False

    @staticmethod
    def order_key(strategy: str) -> str:
        return f"{strategy.replace('-', '_')}_first"

    def samples_for(self, strategy: str) -> List[Sample]:
        if strategy not in self.strategies:
            raise ValueError(f"strategy {strategy!r} is not part of this comparison")
        return [pair.sample_for(strategy) for pair in self.pairs]

    def arm_report(self, strategy: str) -> StageReport:
        """Reuse the ordinary latency accounting without its capacity claims."""
        return StageReport(
            label=f"{self.label}/{strategy}",
            concurrency=self.concurrency,
            wall_seconds=self.wall_seconds,
            samples=self.samples_for(strategy),
            cache_primed=self.cache_primed,
        )

    @property
    def valid_pairs(self) -> List[PairedObservation]:
        return [pair for pair in self.pairs if pair.valid]

    @property
    def semantic_mismatches(self) -> int:
        return sum(pair.semantic_match is False for pair in self.pairs)

    @property
    def order_counts(self) -> Dict[str, int]:
        return {
            self.order_key(strategy): sum(pair.first_strategy == strategy for pair in self.pairs)
            for strategy in self.strategies
        }

    @property
    def order_balanced(self) -> bool:
        counts = list(self.order_counts.values())
        return len(counts) == 2 and counts[0] == counts[1] > 0

    @property
    def alternative_identifier_count(self) -> int:
        # Count each batch once, not once per treatment.
        return sum(pair.alternative_identifier_count for pair in self.pairs)

    @property
    def pairs_with_alternative_identifiers(self) -> int:
        return sum(pair.alternative_identifier_count > 0 for pair in self.pairs)

    @property
    def alternative_order_counts(self) -> Dict[str, int]:
        alternative_pairs = [pair for pair in self.pairs if pair.alternative_identifier_count > 0]
        return {
            self.order_key(strategy): sum(pair.first_strategy == strategy for pair in alternative_pairs)
            for strategy in self.strategies
        }

    @property
    def alternative_order_balanced(self) -> bool:
        counts = list(self.alternative_order_counts.values())
        # An all-PMID comparison has no alternative-ID stratum to balance; its
        # global pair order is still required to be exactly balanced.
        if not any(counts):
            return True
        return len(counts) == 2 and all(count > 0 for count in counts) and abs(counts[0] - counts[1]) <= 1

    # The changed-path stratum depends on the selected implementations, while
    # alternative-ID counts above remain workload information.
    @property
    def changed_path_pair_count(self) -> int:
        return sum(pair.exercises_changed_path for pair in self.pairs)

    @property
    def changed_path_order_counts(self) -> Dict[str, int]:
        changed_pairs = [pair for pair in self.pairs if pair.exercises_changed_path]
        return {
            self.order_key(strategy): sum(pair.first_strategy == strategy for pair in changed_pairs)
            for strategy in self.strategies
        }

    @property
    def changed_path_order_balanced(self) -> bool:
        counts = list(self.changed_path_order_counts.values())
        if not any(counts):
            return True
        return len(counts) == 2 and all(count > 0 for count in counts) and abs(counts[0] - counts[1]) <= 1

    @property
    def unresolved_pairs(self) -> int:
        return sum(pair.unresolved_identifier_count > 0 for pair in self.pairs)

    @property
    def unresolved_identifiers(self) -> int:
        return sum(pair.unresolved_identifier_count for pair in self.pairs)

    @property
    def lookup_fallback_samples(self) -> int:
        return sum(pair.lookup_fallback_samples for pair in self.pairs)

    @property
    def lookup_fallback_attribution_missing(self) -> int:
        return sum(pair.lookup_fallback_attribution_missing for pair in self.pairs)


@dataclass
class ComparisonResult:
    """A single-deployment benchmark of an explicitly ordered strategy pair."""

    plan: RunPlan
    strategies: Tuple[str, str] = DEFAULT_COMPARISON_STRATEGIES
    stages: List[ComparisonStage] = field(default_factory=list)

    @property
    def request_id_mismatches(self) -> int:
        return sum(pair.request_id_mismatches for stage in self.stages for pair in stage.pairs)

    @property
    def lookup_strategy_mismatches(self) -> int:
        return sum(pair.lookup_strategy_mismatches for stage in self.stages for pair in stage.pairs)

    @property
    def semantic_mismatches(self) -> int:
        return sum(stage.semantic_mismatches for stage in self.stages)

    @property
    def unresolved_pairs(self) -> int:
        return sum(stage.unresolved_pairs for stage in self.stages)

    @property
    def unresolved_identifiers(self) -> int:
        return sum(stage.unresolved_identifiers for stage in self.stages)

    @property
    def lookup_fallback_samples(self) -> int:
        return sum(stage.lookup_fallback_samples for stage in self.stages)

    @property
    def lookup_fallback_attribution_missing(self) -> int:
        return sum(stage.lookup_fallback_attribution_missing for stage in self.stages)

    @property
    def invalid_pairs(self) -> int:
        """Pairs excluded because either arm failed or integrity was uncertain."""
        return sum(len(stage.pairs) - len(stage.valid_pairs) for stage in self.stages)

    @property
    def integrity_ok(self) -> bool:
        return bool(self.stages) and all(
            bool(stage.pairs)
            and len(stage.valid_pairs) == len(stage.pairs)
            and stage.strategies == self.strategies
            and stage.order_balanced
            and stage.changed_path_order_balanced
            for stage in self.stages
        )


def _parse_response(
    response: httpx.Response,
    expected_request_id: str,
    expected_lookup_strategy: str,
    capture_semantics: bool = False,
) -> Dict[str, object]:
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
        "lookup_strategy": None,
        "lookup_strategy_matched": True,
        "lookup_fallback": None,
        "semantic_signature": None,
        "error": None,
    }
    if response.status_code != 200:
        return parsed
    try:
        body = response.json()
        meta = body["_meta"]
        results = body["results"]
        not_found = body["not_found"]
        if not isinstance(results, dict) or not isinstance(not_found, list):
            raise TypeError("results must be an object and not_found must be an array")
        parsed["server_ms"] = int(meta["processing_time_ms"])
        parsed["found"] = len(results)
        parsed["not_found"] = len(not_found)
        parsed["request_id_matched"] = meta.get("request_id") == expected_request_id
        observed_lookup_strategy = meta.get("lookup_strategy")
        if isinstance(observed_lookup_strategy, str):
            parsed["lookup_strategy"] = observed_lookup_strategy
        parsed["lookup_strategy_matched"] = observed_lookup_strategy == expected_lookup_strategy
        if not parsed["lookup_strategy_matched"]:
            observed_label = observed_lookup_strategy if observed_lookup_strategy is not None else "<missing>"
            parsed["error"] = f"lookup-strategy-mismatch:expected={expected_lookup_strategy},observed={observed_label}"
        observed_lookup_fallback = meta.get("lookup_fallback")
        if isinstance(observed_lookup_fallback, bool):
            parsed["lookup_fallback"] = observed_lookup_fallback
        if capture_semantics and observed_lookup_fallback is not False:
            fallback_error = (
                "lookup-fallback" if observed_lookup_fallback is True else "lookup-fallback-attribution-missing"
            )
            parsed["error"] = f"{parsed['error']};{fallback_error}" if parsed["error"] else fallback_error
        if capture_semantics:
            semantic_body = {
                "results": results,
                # Ordering is not semantic for the set of identifiers that missed.
                "not_found": sorted(not_found),
            }
            canonical = json.dumps(semantic_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            parsed["semantic_signature"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except (ValueError, KeyError, TypeError) as error:
        parsed["error"] = f"malformed-response:{type(error).__name__}"
    return parsed


async def _issue_request(
    client: httpx.AsyncClient,
    workload: Workload,
    identifiers: List[str],
    capture_semantics: bool = False,
) -> Tuple[Sample, bool, bool]:
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
            True,
        )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0

    parsed = _parse_response(response, request_id, workload.lookup_strategy, capture_semantics=capture_semantics)
    sample = Sample(
        client_ms=elapsed_ms,
        status=response.status_code,
        server_ms=parsed["server_ms"],
        requested=len(identifiers),
        found=parsed["found"],
        not_found=parsed["not_found"],
        response_bytes=len(response.content),
        lookup_strategy=parsed["lookup_strategy"],
        lookup_fallback=parsed["lookup_fallback"],
        semantic_signature=parsed["semantic_signature"],
        error=parsed["error"],
    )
    return sample, bool(parsed["request_id_matched"]), bool(parsed["lookup_strategy_matched"])


async def _worker(
    client: httpx.AsyncClient,
    workload: Workload,
    budget: _Budget,
    seed: Optional[int],
    collected: List[Sample],
    request_id_mismatches: List[int],
    lookup_strategy_mismatches: List[int],
) -> None:
    corpus = workload.build_corpus(seed)
    while budget.claim():
        sample, request_id_matched, lookup_strategy_matched = await _issue_request(
            client, workload, workload.next_batch(corpus)
        )
        collected.append(sample)
        if not request_id_matched:
            request_id_mismatches.append(1)
        if not lookup_strategy_matched:
            lookup_strategy_mismatches.append(1)


async def _run_stage(
    client: httpx.AsyncClient,
    plan: RunPlan,
    concurrency: int,
    total_requests: int,
    seed_offset: int,
) -> Tuple[List[Sample], float, int, int]:
    budget = _Budget(total_requests)
    collected: List[Sample] = []
    request_id_mismatches: List[int] = []
    lookup_strategy_mismatches: List[int] = []
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
                request_id_mismatches,
                lookup_strategy_mismatches,
            )
            for index in range(concurrency)
        )
    )
    return (
        collected,
        time.perf_counter() - started_at,
        len(request_id_mismatches),
        len(lookup_strategy_mismatches),
    )


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

            samples, wall_seconds, request_id_mismatches, lookup_strategy_mismatches = await _run_stage(
                client,
                plan,
                concurrency=concurrency,
                total_requests=plan.requests,
                seed_offset=stage_index,
            )
            result.request_id_mismatches += request_id_mismatches
            result.lookup_strategy_mismatches += lookup_strategy_mismatches
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


@dataclass(frozen=True)
class _ComparisonCase:
    """Precomputed work whose ownership cannot change with treatment speed."""

    index: int
    identifiers: Tuple[str, ...]
    first_strategy: str


class _CaseQueue:
    """Asyncio-safe, non-awaiting allocator for precomputed comparison cases."""

    def __init__(self, cases: List[_ComparisonCase]):
        self.cases = cases
        self.next_index = 0

    def claim(self) -> Optional[_ComparisonCase]:
        if self.next_index >= len(self.cases):
            return None
        case = self.cases[self.next_index]
        self.next_index += 1
        return case


def _comparison_cases(
    workload: Workload,
    total_pairs: int,
    seed: Optional[int],
    seed_offset: int,
    order_offset: int,
    strategies: Tuple[str, str] = DEFAULT_COMPARISON_STRATEGIES,
) -> List[_ComparisonCase]:
    """Draw every batch, then balance order within changed/control strata."""
    if len(strategies) != 2 or strategies[0] == strategies[1]:
        raise ValueError("paired comparison requires two distinct strategies")
    if any(strategy not in SUPPORTED_LOOKUP_STRATEGIES for strategy in strategies):
        raise ValueError(f"comparison strategies must be chosen from {SUPPORTED_LOOKUP_STRATEGIES}")

    corpus_seed = None if seed is None else seed + seed_offset
    corpus = workload.build_corpus(corpus_seed)
    batches = [tuple(workload.next_batch(corpus)) for _ in range(total_pairs)]
    changed_indexes = [
        index for index, identifiers in enumerate(batches) if _exercises_changed_path(identifiers, strategies)
    ]
    changed_index_set = set(changed_indexes)
    control_indexes = [index for index in range(total_pairs) if index not in changed_index_set]

    # The measured pair count is even, so this is exact globally. Supporting an
    # odd warmup count costs nothing and keeps that discarded traffic balanced
    # within one request too.
    global_starts_first = order_offset % 2 == 0
    target_first = (total_pairs + 1) // 2 if global_starts_first else total_pairs // 2
    changed_first = (len(changed_indexes) + 1) // 2 if global_starts_first else len(changed_indexes) // 2
    control_first = target_first - changed_first

    orders: Dict[int, str] = {}

    def assign(indexes: List[int], first_count: int, starts_first: bool) -> None:
        if not indexes:
            return
        lower = len(indexes) // 2
        upper = (len(indexes) + 1) // 2
        if first_count not in (lower, upper):
            raise AssertionError("comparison order allocation is not balanced")
        if lower == upper:
            first_arm_leads = starts_first
        else:
            first_arm_leads = first_count == upper
        for position, index in enumerate(indexes):
            first_arm_is_first = first_arm_leads if position % 2 == 0 else not first_arm_leads
            orders[index] = strategies[0] if first_arm_is_first else strategies[1]

    assign(changed_indexes, changed_first, global_starts_first)
    control_starts_first = global_starts_first if not changed_indexes else not global_starts_first
    assign(control_indexes, control_first, control_starts_first)
    return [
        _ComparisonCase(
            index=index,
            identifiers=identifiers,
            first_strategy=orders[index],
        )
        for index, identifiers in enumerate(batches)
    ]


async def _comparison_worker(
    client: httpx.AsyncClient,
    queue: _CaseQueue,
    workloads: Dict[str, Workload],
    strategies: Tuple[str, str],
    collected: List[PairedObservation],
) -> None:
    while True:
        case = queue.claim()
        if case is None:
            return

        second_strategy = strategies[1] if case.first_strategy == strategies[0] else strategies[0]
        samples: Dict[str, Sample] = {}
        request_id_mismatches = 0
        lookup_strategy_mismatches = 0
        for strategy in (case.first_strategy, second_strategy):
            sample, request_id_matched, lookup_strategy_matched = await _issue_request(
                client,
                workloads[strategy],
                list(case.identifiers),
                capture_semantics=True,
            )
            samples[strategy] = sample
            request_id_mismatches += int(not request_id_matched)
            lookup_strategy_mismatches += int(not lookup_strategy_matched)

        first_sample = samples[strategies[0]]
        second_sample = samples[strategies[1]]
        semantic_match = None
        if first_sample.semantic_signature is not None and second_sample.semantic_signature is not None:
            semantic_match = first_sample.semantic_signature == second_sample.semantic_signature
        collected.append(
            PairedObservation(
                index=case.index,
                first_strategy=case.first_strategy,
                identifiers=case.identifiers,
                samples=samples,
                strategies=strategies,
                request_id_mismatches=request_id_mismatches,
                lookup_strategy_mismatches=lookup_strategy_mismatches,
                semantic_match=semantic_match,
            )
        )


async def _run_comparison_stage(
    client: httpx.AsyncClient,
    plan: RunPlan,
    concurrency: int,
    total_pairs: int,
    seed_offset: int,
    order_offset: int,
    strategies: Tuple[str, str] = DEFAULT_COMPARISON_STRATEGIES,
) -> Tuple[List[PairedObservation], float]:
    cases = _comparison_cases(
        plan.workload,
        total_pairs,
        plan.seed,
        seed_offset,
        order_offset,
        strategies=strategies,
    )
    queue = _CaseQueue(cases)
    collected: List[PairedObservation] = []
    workloads = {strategy: replace(plan.workload, lookup_strategy=strategy) for strategy in strategies}

    started_at = time.perf_counter()
    await asyncio.gather(
        *(
            _comparison_worker(client, queue, workloads, strategies, collected)
            for _ in range(min(concurrency, total_pairs))
        )
    )
    return sorted(collected, key=lambda pair: pair.index), time.perf_counter() - started_at


async def run_comparison_plan(
    plan: RunPlan,
    cache_primed: bool = False,
    strategies: Tuple[str, str] = DEFAULT_COMPARISON_STRATEGIES,
) -> ComparisonResult:
    """Run a balanced comparison of two lookup strategies on one deployment.

    ``concurrency`` remains the maximum number of HTTP requests in flight. A
    worker issues the two members of its pair sequentially; starting both at
    once would double load and let the treatments directly contend with each
    other. Alternating which treatment goes first balances, but cannot remove,
    the shared-backend cache effect.
    """
    if plan.requests < 2 or plan.requests % 2:
        raise ValueError("paired comparison requires an even --requests value of at least 2")
    if not plan.workload.uses_identifier_pool:
        raise ValueError("paired comparison requires a real --identifier-file corpus")
    if len(strategies) != 2 or strategies[0] == strategies[1]:
        raise ValueError("paired comparison requires two distinct strategies")
    if any(strategy not in SUPPORTED_LOOKUP_STRATEGIES for strategy in strategies):
        raise ValueError(f"comparison strategies must be chosen from {SUPPORTED_LOOKUP_STRATEGIES}")

    result = ComparisonResult(plan=plan, strategies=strategies)
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
                await _run_comparison_stage(
                    client,
                    plan,
                    concurrency=min(concurrency, plan.warmup_requests),
                    total_pairs=plan.warmup_requests,
                    seed_offset=-(stage_index + 1),
                    order_offset=stage_index + 1,
                    strategies=strategies,
                )

            pairs, wall_seconds = await _run_comparison_stage(
                client,
                plan,
                concurrency=concurrency,
                total_pairs=plan.requests,
                seed_offset=stage_index,
                order_offset=stage_index,
                strategies=strategies,
            )
            stage = ComparisonStage(
                label=f"c={concurrency}",
                concurrency=concurrency,
                wall_seconds=wall_seconds,
                strategies=strategies,
                pairs=pairs,
                cache_primed=cache_primed,
            )
            result.stages.append(stage)
    return result


async def verify_pmid_pool(
    base_url: str,
    candidates: List[str],
    timeout_seconds: float = 30.0,
    lookup_strategy: str = "current",
) -> List[str]:
    """Return the subset of ``candidates`` the deployment can actually resolve.

    Calling this primes the backend cache for every identifier it confirms, so a
    run measured against a verified pool reports warm-cache latency. Runs that
    use it are labelled ``cache_primed`` for that reason.
    """
    if lookup_strategy not in SUPPORTED_LOOKUP_STRATEGIES:
        raise ValueError(f"lookup_strategy must be one of {SUPPORTED_LOOKUP_STRATEGIES}")

    resolved: List[str] = []
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds) as client:
        for start in range(0, len(candidates), 100):
            chunk = candidates[start : start + 100]
            response = await client.post(
                "/publications",
                json={"ids": chunk, "request_id": "corpus-verify"},
                headers={LOOKUP_STRATEGY_HEADER: lookup_strategy},
            )
            response.raise_for_status()
            body = response.json()
            observed_lookup_strategy = body.get("_meta", {}).get("lookup_strategy")
            if observed_lookup_strategy != lookup_strategy:
                observed_label = observed_lookup_strategy if observed_lookup_strategy is not None else "<missing>"
                raise RuntimeError(
                    f"lookup strategy mismatch during corpus verification: "
                    f"expected={lookup_strategy}, observed={observed_label}"
                )
            resolved.extend(body["results"].keys())
    return resolved
