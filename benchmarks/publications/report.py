"""Rendering for ``/publications`` benchmark results."""

import json
from typing import Dict, List, Optional

from benchmarks.publications.metrics import SLO_QUANTILE, LatencySummary, StageReport
from benchmarks.publications.runner import RunResult
from benchmarks.publications.users import MIN_STEADY_STATE_THINK_TIMES, capacity_table

_COLUMNS = (
    ("stage", 7),
    ("rps", 7),
    ("batch", 6),
    ("found", 6),
    ("resp kB", 8),
    ("server p50", 11),
    ("server p90", 11),
    ("server p99", 11),
    ("client p50", 11),
    ("client p90", 11),
    ("client p99", 11),
    ("net p90", 8),
)


def _cell(value: object, width: int) -> str:
    return f"{value:>{width}}"


def _latency_cells(summary: Optional[LatencySummary]) -> List[str]:
    if summary is None:
        return ["-", "-", "-"]
    return [f"{summary.p50:.0f}", f"{summary.p90:.0f}", f"{summary.p99:.0f}"]


def _stage_row(stage: StageReport) -> str:
    identifiers = stage.identifier_stats
    server = _latency_cells(stage.server_latency())
    client = _latency_cells(stage.client_latency())
    overhead = stage.overhead_latency()
    values = [
        stage.label,
        f"{stage.throughput_rps:.1f}",
        identifiers.get("mean_batch_size", "-"),
        f"{identifiers.get('found_ratio', 0) * 100:.0f}%" if identifiers.get("requests") else "-",
        identifiers.get("mean_response_kb", "-"),
        *server,
        *client,
        f"{overhead.p90:.0f}" if overhead else "-",
    ]
    return "".join(_cell(value, width) for value, (_, width) in zip(values, _COLUMNS))


# A stage shedding more than this fraction of its load is not serving that load,
# whatever its surviving requests did for latency.
MIN_CEILING_SUCCESS_RATE = 0.99


def sustained_ceiling(result: RunResult) -> Optional[StageReport]:
    """The highest-throughput stage that met the objective *and* stayed healthy.

    This is the capacity number a user count has to be derived from, and it takes
    two conditions rather than one. Latency alone is not enough: because failures
    are excluded from the percentiles, a stage that answers a tenth of its load
    with 500s can post a better p90 than a stage that serves everything. Reading
    a ceiling off that would recommend a load level at which the service is
    already erroring, so the success rate gates it too.
    """
    passing = [
        stage
        for stage in result.stages
        if (verdict := stage.verdict("server", result.plan.threshold_ms)) is not None
        and verdict.met
        and stage.success_rate >= MIN_CEILING_SUCCESS_RATE
    ]
    return max(passing, key=lambda stage: stage.throughput_rps, default=None)


def _capacity_lines(result: RunResult) -> List[str]:
    """Translate a measured ceiling into supported user counts.

    Derived from the fastest *passing* stage rather than from whatever throughput
    the run happened to produce. In a user-model run that distinction matters: if
    the population was served without saturating the service, its achieved rate
    reflects the load offered, not the load available, and reading a user ceiling
    off it would just restate the input.
    """
    ceiling = sustained_ceiling(result)
    if ceiling is None:
        degraded = [
            f"{stage.label} ({stage.success_rate:.1%} success)"
            for stage in result.stages
            if stage.success_rate < MIN_CEILING_SUCCESS_RATE
        ]
        reason = (
            f"every stage either missed the objective or shed load: {', '.join(degraded)}"
            if degraded
            else "no stage met the objective"
        )
        return ["", f"no sustained capacity to report — {reason}"]

    server = ceiling.server_latency()
    if server is None:
        return []

    lines = [
        "",
        "supported users, by Little's Law",
        "  users = throughput x (service latency + think time)",
        f"  from the fastest passing stage: {ceiling.label} at "
        f"{ceiling.throughput_rps:.1f} rps, {server.p90:.0f} ms p90",
    ]
    for row in capacity_table(ceiling.throughput_rps, server.p90):
        lines.append(
            f"    {row['think_time_seconds']:>5.0f}s think time  "
            f"{row['supported_users']:>7,.0f} users  "
            f"({row['requests_per_user_rps']:.4f} rps each)"
        )
    return lines


def _user_lines(result: RunResult) -> List[str]:
    """Render the population view: what was offered, and what was served."""
    model = result.user_model
    if model is None:
        return []

    stage = result.stages[0]
    achieved = stage.throughput_rps
    offered = model.offered_rate_rps
    # A population that offers more than the service accepts is backing up: the
    # deficit is requests its users are still waiting on rather than issuing.
    shortfall = (offered - achieved) / offered if offered else 0.0
    # Only trust the rate comparison once the joining transient has washed out.
    # Before that the achieved rate reads high and a saturated run can look as
    # though it kept up.
    saturated = shortfall > 0.05 and model.reaches_steady_state

    lines = [
        "",
        "population",
        f"  simulated          {model.users} users at {model.think_time_seconds:g}s mean think time",
        f"  offered rate       {offered:.1f} rps",
        f"  achieved rate      {achieved:.1f} rps"
        # Deliberately not phrased as "the service did not keep up": the next
        # line works out which end the shortfall came from.
        + (f"  ({shortfall:.0%} short of offered)" if saturated else "  (kept up)"),
        f"  catalogue          {model.catalog_size} papers, zipf {model.zipf_exponent:g}",
    ]

    identifiers = stage.identifier_stats
    if identifiers.get("requests"):
        lines.append(
            f"  mean batch sent    {identifiers['mean_batch_size']:.0f} of {result.plan.workload.batch_size} "
            "requested, after a skewed draw collapsed repeats"
        )
    if not model.reaches_steady_state:
        lines.append(
            f"  the run covers {model.think_times_elapsed:.1f} think times, so every user's joining request "
            f"is still a large share of the total and the achieved rate reads roughly "
            f"{1 / (2 * model.think_times_elapsed):.0%} high. Latency is unaffected; for a trustworthy rate "
            f"comparison run at least {MIN_STEADY_STATE_THINK_TIMES * model.think_time_seconds:.0f}s"
        )
    elif not saturated:
        lines.append(
            "  this population was served without saturating the service, so it bounds nothing from above; "
            "use --ramp to find the ceiling"
        )
    else:
        server = stage.server_latency()
        healthy = server is not None and server.p90 < result.plan.threshold_ms
        if healthy and stage.success_rate >= MIN_CEILING_SUCCESS_RATE:
            # The discriminator: server-side latency is measured in-handler, so
            # if it is healthy while the offered rate goes unmet, the load
            # generator is the more likely constraint. One machine driving this
            # many connections has to decompress and parse every response.
            lines.append(
                "  the shortfall came with a healthy server-side p90 and no errors, which points at the "
                "load generator rather than the service — one host driving this many connections must "
                "decompress and parse every response. Re-run from inside the cluster, or split the "
                "generator across hosts, before reading this as the service's ceiling"
            )
    return lines


def render_text(result: RunResult) -> str:
    """Render a run as an aligned latency table with an SLO verdict per stage."""
    plan = result.plan
    threshold = plan.threshold_ms
    lines = [
        "/publications load benchmark",
        f"  target     {plan.normalized_base_url}",
        f"  workload   {plan.workload.describe()}",
        (
            f"  load       {result.user_model.users} simulated users for "
            f"{result.user_model.duration_seconds:g}s, {plan.timeout_seconds:g}s timeout"
            if result.user_model is not None
            else f"  load       {plan.requests} measured requests per stage, "
            f"{plan.warmup_requests} discarded warmup, {plan.timeout_seconds:g}s timeout"
        ),
        f"  objective  p90 < {threshold:g} ms at the 90th percentile (CCWG#15)",
        "",
        "latency in milliseconds; net = client minus server, i.e. transit and transfer",
        "".join(_cell(name, width) for name, width in _COLUMNS),
        "-" * sum(width for _, width in _COLUMNS),
    ]
    lines.extend(_stage_row(stage) for stage in result.stages)
    lines.append("")

    lines.append("SLO verdict")
    for stage in result.stages:
        for basis in ("server", "client"):
            verdict = stage.verdict(basis, threshold)
            if verdict is None:
                lines.append(f"  {stage.label:<7} {basis:<7} no successful samples")
                continue
            status = "PASS" if verdict.met else "FAIL"
            # A stage can post a passing p90 while shedding load, because the
            # shed requests are not in the distribution. Flag it inline rather
            # than leaving it to the status-code block further down.
            shedding = (
                ""
                if stage.success_rate >= MIN_CEILING_SUCCESS_RATE
                else (f"  [only {stage.success_rate:.1%} succeeded — not sustained]")
            )
            lines.append(
                f"  {stage.label:<7} {basis:<7} {status}  "
                f"p90 {verdict.p90_ms:>7.1f} ms  "
                f"{verdict.fraction_under_threshold:>6.1%} under {threshold:g} ms  "
                f"headroom {verdict.headroom_ms:>+8.1f} ms{shedding}"
            )

    failures = {
        status: count for stage in result.stages for status, count in stage.status_counts.items() if status != "200"
    }
    if failures:
        lines.extend(["", f"non-200 and transport failures  {failures}"])
    if result.request_id_mismatches:
        lines.append(f"request_id round-trip mismatches  {result.request_id_mismatches}")

    lines.extend(_user_lines(result))
    lines.extend(_capacity_lines(result))

    notes = _caveats(result)
    if notes:
        lines.append("")
        lines.append("read this with")
        lines.extend(f"  - {note}" for note in notes)
    return "\n".join(lines)


def _caveats(result: RunResult) -> List[str]:
    """Conditions that change how the numbers should be read.

    These are emitted from the observed run rather than assumed, so a report
    always carries the caveats that actually apply to it.
    """
    notes: List[str] = []
    plan = result.plan
    notes.append(
        "the supported-user figures follow from the think-time assumption, which is a claim about reader "
        "behaviour rather than something this benchmark measures; treat the range as the answer"
    )
    overheads = [stage.overhead_latency() for stage in result.stages]
    measured = [summary.p90 for summary in overheads if summary is not None]
    if measured and max(measured) > 20:
        notes.append(
            f"network overhead adds up to {max(measured):.0f} ms at p90 from this vantage point, "
            "so the client-side verdict is specific to where this ran; the server-side verdict is not"
        )
    if any(stage.cache_primed for stage in result.stages):
        notes.append(
            "the corpus was verified before measuring, which primes the backend cache: "
            "these are warm-cache latencies, not what a first-time lookup costs"
        )
    if plan.workload.uses_identifier_pool:
        notes.append(
            f"requests sample repeatedly from a fixed pool of {len(plan.workload.identifier_pool)} real identifiers, "
            "so backend caches can warm during the run"
        )
    elif plan.workload.unique_ratio >= 1.0 and result.user_model is None:
        notes.append(
            "every identifier is drawn fresh, so this is the cold-cache bound; "
            "re-run with --unique-ratio below 1.0 for the cached case"
        )
    if not plan.workload.uses_identifier_pool and plan.workload.pmid_ratio < 1.0:
        notes.append(
            "the default mixed workload synthesizes PMCID and DOI values that usually report not_found; "
            "they exercise the bulk alternative-identifier search miss path, so use --identifier-file "
            "with real resolving identifiers to measure hit-path work"
        )
    found_ratios = [
        stage.identifier_stats.get("found_ratio", 0.0)
        for stage in result.stages
        if stage.identifier_stats.get("requests")
    ]
    if found_ratios and max(found_ratios) < 0.5:
        notes.append(
            f"only {max(found_ratios):.0%} of identifiers resolved, so most of the measured work was "
            "a miss; a miss is cheaper to serve than a hit and this understates real latency"
        )
    return notes


def render_json(result: RunResult) -> str:
    return json.dumps(as_dict(result), indent=2)


def as_dict(result: RunResult) -> Dict[str, object]:
    plan = result.plan
    return {
        "target": plan.normalized_base_url,
        "objective": {
            "source": "NCATSTranslator/Core-Components-Working-Group#15",
            "threshold_ms": plan.threshold_ms,
            "quantile": SLO_QUANTILE,
        },
        "workload": {
            "description": plan.workload.describe(),
            "batch_size": plan.workload.batch_size,
            "method": plan.workload.normalized_method,
            "pmid_ratio": None if plan.workload.uses_identifier_pool else plan.workload.pmid_ratio,
            "unique_ratio": None if plan.workload.uses_identifier_pool else plan.workload.unique_ratio,
            "identifier_pool": (
                {
                    "source": plan.workload.identifier_pool_source or "provided pool",
                    "size": len(plan.workload.identifier_pool),
                }
                if plan.workload.uses_identifier_pool
                else None
            ),
        },
        "load": {
            "requests_per_stage": plan.requests,
            "warmup_requests": plan.warmup_requests,
            "timeout_seconds": plan.timeout_seconds,
            "stages": list(plan.stages),
            "seed": plan.seed,
        },
        "user_model": (
            {
                "users": result.user_model.users,
                "think_time_seconds": result.user_model.think_time_seconds,
                "duration_seconds": result.user_model.duration_seconds,
                "offered_rate_rps": round(result.user_model.offered_rate_rps, 3),
                "catalog_size": result.user_model.catalog_size,
                "zipf_exponent": result.user_model.zipf_exponent,
            }
            if result.user_model is not None
            else None
        ),
        "request_id_mismatches": result.request_id_mismatches,
        "caveats": _caveats(result),
        "stages": [stage.as_dict(plan.threshold_ms) for stage in result.stages],
    }


def slo_met(result: RunResult, basis: str) -> bool:
    """Whether every stage met the objective on ``basis``.

    A run with no successful samples or mismatched request correlation does not
    count as meeting the objective.
    """
    if result.request_id_mismatches:
        return False
    verdicts = [stage.verdict(basis, result.plan.threshold_ms) for stage in result.stages]
    return bool(verdicts) and all(verdict is not None and verdict.met for verdict in verdicts)
