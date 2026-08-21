"""Command line entry point for the ``/publications`` load benchmark.

python -m benchmarks.publications --help
"""

import argparse
import asyncio
import sys
from typing import List, Optional, Sequence, Tuple

from benchmarks.publications.corpus import (
    DEFAULT_MAX_PMID,
    DEFAULT_MIN_PMID,
    CorpusConfig,
    IdentifierCorpus,
)
from benchmarks.publications.metrics import SLO_THRESHOLD_MS
from benchmarks.publications.report import render_json, render_text, slo_met
from benchmarks.publications.runner import RunResult, run_plan, verify_pmid_pool
from benchmarks.publications.workload import DEFAULT_BATCH_SIZE, RunPlan, Workload

# CI is the deployment CCWG#15 is being validated against.
DEFAULT_BASE_URL = "https://annotator.ci.transltr.io"


def _ramp_levels(value: str) -> List[int]:
    levels = [int(part) for part in value.split(",") if part.strip()]
    if not levels:
        raise argparse.ArgumentTypeError("ramp must list at least one concurrency level")
    if any(level < 1 for level in levels):
        raise argparse.ArgumentTypeError("every ramp level must be >= 1")
    return levels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.publications",
        description=(
            "Load-test the /publications endpoint against the 150 ms p90 objective in "
            "NCATSTranslator/Core-Components-Working-Group#15."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="deployment to measure")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="identifiers per request; CCWG#15 caps this at 100",
    )
    parser.add_argument("--method", choices=("GET", "POST", "get", "post"), default="GET")
    parser.add_argument("--requests", type=int, default=100, help="measured requests per stage")
    parser.add_argument("--concurrency", type=int, default=1, help="concurrent requests in flight")
    parser.add_argument(
        "--ramp",
        type=_ramp_levels,
        default=None,
        metavar="1,2,4,8",
        help="sweep these concurrency levels instead of a single --concurrency stage",
    )
    parser.add_argument("--warmup", type=int, default=10, help="discarded requests before each stage")
    parser.add_argument(
        "--pmid-ratio",
        type=float,
        default=1.0,
        help="fraction of each batch drawn as PMIDs; the remainder is PMCID and DOI",
    )
    parser.add_argument(
        "--unique-ratio",
        type=float,
        default=1.0,
        help="fraction drawn fresh; 1.0 is the cold-cache bound, lower replays identifiers",
    )
    parser.add_argument("--hot-pool", type=int, default=1_000, help="identifiers available for replay")
    parser.add_argument("--min-pmid", type=int, default=DEFAULT_MIN_PMID, help=argparse.SUPPRESS)
    parser.add_argument("--max-pmid", type=int, default=DEFAULT_MAX_PMID, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request timeout in seconds")
    parser.add_argument("--threshold-ms", type=float, default=SLO_THRESHOLD_MS, help="p90 objective")
    parser.add_argument("--seed", type=int, default=None, help="seed the identifier draw for a repeatable run")
    parser.add_argument(
        "--verify-corpus",
        type=int,
        default=0,
        metavar="N",
        help=(
            "confirm N PMIDs resolve before measuring and replay only those. This primes the backend "
            "cache, so the run reports warm-cache latency and is labelled as such"
        ),
    )
    parser.add_argument(
        "--slo-basis",
        choices=("server", "client"),
        default="server",
        help=(
            "which latency decides the exit code. 'server' is the endpoint's own processing_time_ms "
            "and is comparable from any vantage point; 'client' is end-to-end and includes the "
            "network path from wherever this runs"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output only")
    return parser


async def _prepare_workload(arguments: argparse.Namespace) -> Tuple[Workload, bool]:
    """Build the workload, resolving a verified corpus when one was requested."""
    workload = Workload(
        batch_size=arguments.batch_size,
        method=arguments.method,
        pmid_ratio=arguments.pmid_ratio,
        unique_ratio=arguments.unique_ratio,
        hot_pool_size=arguments.hot_pool,
    )
    if not arguments.verify_corpus:
        return workload, False

    # Over-draw to absorb the identifiers that do not resolve, so the verified
    # pool reaches the requested size in one pass rather than looping.
    candidate_count = int(arguments.verify_corpus * 1.3) + arguments.batch_size
    sampler = IdentifierCorpus(
        CorpusConfig(min_pmid=arguments.min_pmid, max_pmid=arguments.max_pmid, seed=arguments.seed)
    )
    candidates = [sampler.fresh_pmid() for _ in range(candidate_count)]
    resolved = await verify_pmid_pool(arguments.base_url, candidates, arguments.timeout)
    if len(resolved) < arguments.batch_size:
        raise SystemExit(
            f"corpus verification resolved only {len(resolved)} identifiers, "
            f"which cannot fill a batch of {arguments.batch_size}"
        )
    return (
        Workload(
            batch_size=arguments.batch_size,
            method=arguments.method,
            pmid_ratio=arguments.pmid_ratio,
            # A verified corpus exists precisely so the run replays known-present
            # identifiers, which is only meaningful with reuse enabled.
            unique_ratio=0.0,
            hot_pool_size=len(resolved),
        ),
        True,
    )


async def execute(arguments: argparse.Namespace) -> RunResult:
    workload, cache_primed = await _prepare_workload(arguments)
    plan = RunPlan(
        base_url=arguments.base_url,
        workload=workload,
        concurrency=arguments.concurrency,
        requests=arguments.requests,
        warmup_requests=arguments.warmup,
        timeout_seconds=arguments.timeout,
        seed=arguments.seed,
        threshold_ms=arguments.threshold_ms,
        ramp=tuple(arguments.ramp or ()),
    )
    return await run_plan(plan, cache_primed=cache_primed)


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = asyncio.run(execute(arguments))
    print(render_json(result) if arguments.json else render_text(result))
    return 0 if slo_met(result, arguments.slo_basis) else 1


if __name__ == "__main__":
    sys.exit(main())
