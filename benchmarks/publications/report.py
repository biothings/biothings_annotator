"""Rendering for ``/publications`` benchmark results."""

import json
from typing import Dict, List, Optional, Union

from benchmarks.publications.metrics import SLO_QUANTILE, LatencySummary, StageReport
from benchmarks.publications.runner import ComparisonResult, ComparisonStage, PairedObservation, RunResult
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

_COMPARISON_COLUMNS = (
    ("stage", 7),
    ("strategy", 12),
    ("ok", 9),
    ("found", 7),
    ("resp kB", 9),
    ("server p50", 12),
    ("server p90", 12),
    ("server p99", 12),
    ("client p50", 12),
    ("client p90", 12),
    ("client p99", 12),
)

BenchmarkResult = Union[RunResult, ComparisonResult]


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


def _comparison_arm_row(stage: ComparisonStage, strategy: str) -> str:
    arm = stage.arm_report(strategy)
    identifiers = arm.identifier_stats
    values = [
        stage.label,
        strategy,
        f"{len(arm.successful)}/{len(arm.samples)}",
        f"{identifiers.get('found_ratio', 0) * 100:.0f}%" if identifiers.get("requests") else "-",
        identifiers.get("mean_response_kb", "-"),
        *_latency_cells(arm.server_latency()),
        *_latency_cells(arm.client_latency()),
    ]
    return "".join(_cell(value, width) for value, (_, width) in zip(values, _COMPARISON_COLUMNS))


def _pair_latency(pair: PairedObservation, strategy: str, basis: str) -> Optional[float]:
    sample = pair.current if strategy == "current" else pair.bulk_search
    if basis == "client":
        return sample.client_ms
    if basis == "server":
        return float(sample.server_ms) if sample.server_ms is not None else None
    raise ValueError("basis must be 'client' or 'server'")


def _paired_delta_values(
    stage: ComparisonStage,
    basis: str,
    first_strategy: Optional[str] = None,
) -> List[float]:
    values: List[float] = []
    for pair in stage.valid_pairs:
        if first_strategy is not None and pair.first_strategy != first_strategy:
            continue
        current = _pair_latency(pair, "current", basis)
        bulk_search = _pair_latency(pair, "bulk-search", basis)
        if current is not None and bulk_search is not None:
            values.append(bulk_search - current)
    return values


def _delta_summary(values: List[float]) -> Optional[Dict[str, object]]:
    summary = LatencySummary.from_values(values)
    if summary is None:
        return None
    rendered: Dict[str, object] = summary.as_dict()
    rendered["bulk_search_faster_fraction"] = round(sum(value < 0 for value in values) / len(values), 4)
    return rendered


def _comparison_delta_dict(stage: ComparisonStage, basis: str) -> Dict[str, object]:
    return {
        "all": _delta_summary(_paired_delta_values(stage, basis)),
        "current_first": _delta_summary(_paired_delta_values(stage, basis, "current")),
        "bulk_search_first": _delta_summary(_paired_delta_values(stage, basis, "bulk-search")),
    }


def _comparison_p90_difference(stage: ComparisonStage, basis: str) -> Optional[float]:
    current = (
        stage.arm_report("current").server_latency()
        if basis == "server"
        else stage.arm_report("current").client_latency()
    )
    bulk_search = (
        stage.arm_report("bulk-search").server_latency()
        if basis == "server"
        else stage.arm_report("bulk-search").client_latency()
    )
    if current is None or bulk_search is None:
        return None
    return round(bulk_search.p90 - current.p90, 2)


def _comparison_p90_percent(stage: ComparisonStage, basis: str) -> Optional[float]:
    current = (
        stage.arm_report("current").server_latency()
        if basis == "server"
        else stage.arm_report("current").client_latency()
    )
    bulk_search = (
        stage.arm_report("bulk-search").server_latency()
        if basis == "server"
        else stage.arm_report("bulk-search").client_latency()
    )
    if current is None or bulk_search is None or current.p90 == 0:
        return None
    return round((bulk_search.p90 - current.p90) / current.p90 * 100, 2)


def _comparison_arm_dict(stage: ComparisonStage, strategy: str, threshold_ms: float) -> Dict[str, object]:
    arm = stage.arm_report(strategy)
    client = arm.client_latency()
    server = arm.server_latency()
    overhead = arm.overhead_latency()
    client_verdict = arm.verdict("client", threshold_ms)
    server_verdict = arm.verdict("server", threshold_ms)
    return {
        "requests": len(arm.samples),
        "successful": len(arm.successful),
        "success_rate": round(arm.success_rate, 4),
        "status_counts": arm.status_counts,
        "lookup_strategy_counts": arm.lookup_strategy_counts,
        "identifiers": arm.identifier_stats,
        "client_latency": client.as_dict() if client else None,
        "server_latency": server.as_dict() if server else None,
        "network_overhead": overhead.as_dict() if overhead else None,
        "slo": {
            "client": client_verdict.as_dict() if client_verdict else None,
            "server": server_verdict.as_dict() if server_verdict else None,
        },
    }


def _comparison_stage_dict(stage: ComparisonStage, threshold_ms: float) -> Dict[str, object]:
    return {
        "label": stage.label,
        "concurrency": stage.concurrency,
        "wall_seconds": round(stage.wall_seconds, 3),
        "pairs": len(stage.pairs),
        "valid_pairs": len(stage.valid_pairs),
        "invalid_pairs": len(stage.pairs) - len(stage.valid_pairs),
        "order_counts": stage.order_counts,
        "order_balanced": stage.order_balanced,
        "changed_path_order_counts": stage.changed_path_order_counts,
        "changed_path_order_balanced": stage.changed_path_order_balanced,
        "alternative_identifiers": stage.alternative_identifier_count,
        "pairs_with_alternative_identifiers": stage.pairs_with_alternative_identifiers,
        "integrity": {
            "request_id_mismatches": sum(pair.request_id_mismatches for pair in stage.pairs),
            "lookup_strategy_mismatches": sum(pair.lookup_strategy_mismatches for pair in stage.pairs),
            "semantic_mismatches": stage.semantic_mismatches,
            "unresolved_pairs": stage.unresolved_pairs,
            "unresolved_identifiers": stage.unresolved_identifiers,
        },
        "arms": {
            strategy: _comparison_arm_dict(stage, strategy, threshold_ms) for strategy in ("current", "bulk-search")
        },
        "p90_difference_ms": {
            "server": _comparison_p90_difference(stage, "server"),
            "client": _comparison_p90_difference(stage, "client"),
        },
        "p90_difference_percent": {
            "server": _comparison_p90_percent(stage, "server"),
            "client": _comparison_p90_percent(stage, "client"),
        },
        "paired_delta_ms": {
            "meaning": "bulk-search minus current; negative is faster",
            "server": _comparison_delta_dict(stage, "server"),
            "client": _comparison_delta_dict(stage, "client"),
        },
    }


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


def _comparison_delta_line(
    stage: ComparisonStage,
    basis: str,
    label: str,
    first_strategy: Optional[str] = None,
) -> str:
    values = _paired_delta_values(stage, basis, first_strategy)
    summary = LatencySummary.from_values(values)
    if summary is None:
        return f"  {stage.label:<7} {basis:<7} {label:<17} no valid pairs"
    faster = sum(value < 0 for value in values) / len(values)
    return (
        f"  {stage.label:<7} {basis:<7} {label:<17} n={summary.count:<4} "
        f"p50 {summary.p50:>+7.1f}  p90 {summary.p90:>+7.1f}  p99 {summary.p99:>+7.1f}  "
        f"bulk-search faster {faster:>6.1%}"
    )


def _comparison_caveats(result: ComparisonResult) -> List[str]:
    notes = [
        "each pair is sequential, so its second request can benefit from Elasticsearch state warmed by its "
        "first; balanced current-first/bulk-search-first ordering controls first-order bias but cannot produce two "
        "cold observations on one shared deployment",
        "the two implementations share one mixed load during this run, so its wall time is not a standalone "
        "capacity measurement; use single-strategy --ramp runs for absolute capacity",
    ]
    if any(stage.cache_primed for stage in result.stages):
        notes.append(
            "the corpus was verified before measuring, which primes the backend cache: these are warm-cache "
            "latencies"
        )
    if result.plan.workload.uses_identifier_pool:
        notes.append(
            f"pairs sample repeatedly from a fixed pool of {len(result.plan.workload.identifier_pool)} real "
            "identifiers, so the backend continues to warm during the run"
        )
    elif result.plan.workload.pmid_ratio < 1.0:
        notes.append(
            "the synthesized PMCID and DOI values usually miss; use --identifier-file with resolving identifiers "
            "before deciding between source-fetch strategies"
        )
    overheads = [
        arm.overhead_latency()
        for stage in result.stages
        for arm in (stage.arm_report("current"), stage.arm_report("bulk-search"))
    ]
    measured = [summary.p90 for summary in overheads if summary is not None]
    if measured and max(measured) > 20:
        notes.append(
            f"network overhead adds up to {max(measured):.0f} ms at p90 from this vantage point; use server "
            "latency for the implementation decision"
        )
    for stage in result.stages:
        if not stage.changed_path_order_balanced:
            notes.append(
                f"{stage.label} does not contain a balanced changed-path pair in both request orders; "
                "do not declare a winner"
            )
        if stage.pairs_with_alternative_identifiers < len(stage.pairs):
            notes.append(
                f"{stage.label} has {len(stage.pairs) - stage.pairs_with_alternative_identifiers} PMID-only pairs "
                "that do not exercise the changed DOI/PMCID path; use the reported identifier mix when judging "
                "the combined delta"
            )
        current_first = LatencySummary.from_values(_paired_delta_values(stage, "server", "current"))
        bulk_search_first = LatencySummary.from_values(_paired_delta_values(stage, "server", "bulk-search"))
        if current_first and bulk_search_first and current_first.p50 * bulk_search_first.p50 <= 0:
            notes.append(
                f"{stage.label} has zero or opposite-signed median server deltas between current-first "
                "and bulk-search-first pairs; the result is order/cache-sensitive, so do not declare a winner"
            )
    return notes


def _comparison_workload_description(result: ComparisonResult) -> str:
    description = result.plan.workload.describe()
    suffix = f", {result.plan.workload.lookup_strategy} lookup"
    if description.endswith(suffix):
        description = description[: -len(suffix)]
    return f"{description}, paired current vs bulk-search"


def _render_comparison_text(result: ComparisonResult) -> str:
    plan = result.plan
    lines = [
        "/publications paired lookup-strategy benchmark",
        f"  target     {plan.normalized_base_url}",
        f"  workload   {_comparison_workload_description(result)}",
        f"  load       {plan.requests} measured pairs per stage ({plan.requests * 2} HTTP requests), "
        f"{plan.warmup_requests} discarded warmup pairs, {plan.timeout_seconds:g}s timeout",
        f"  objective  p90 < {plan.threshold_ms:g} ms at the 90th percentile (CCWG#15)",
        "",
        "per-arm latency in milliseconds; mixed-run wall time is not standalone throughput",
        "".join(_cell(name, width) for name, width in _COMPARISON_COLUMNS),
        "-" * sum(width for _, width in _COMPARISON_COLUMNS),
    ]
    for stage in result.stages:
        lines.extend(_comparison_arm_row(stage, strategy) for strategy in ("current", "bulk-search"))

    lines.extend(["", "per-arm p90 difference (bulk-search minus current)"])
    for stage in result.stages:
        differences = []
        for basis in ("server", "client"):
            difference = _comparison_p90_difference(stage, basis)
            percent = _comparison_p90_percent(stage, basis)
            if difference is None or percent is None:
                differences.append(f"{basis} unavailable")
            else:
                differences.append(f"{basis} {difference:+.1f} ms ({percent:+.1f}%)")
        lines.append(f"  {stage.label:<7} " + ", ".join(differences))

    lines.extend(["", "paired delta in milliseconds (bulk-search minus current; negative is faster)"])
    for stage in result.stages:
        for basis in ("server", "client"):
            lines.append(_comparison_delta_line(stage, basis, "all"))
            lines.append(_comparison_delta_line(stage, basis, "current-first", "current"))
            lines.append(_comparison_delta_line(stage, basis, "bulk-search-first", "bulk-search"))

    lines.extend(["", "SLO verdict by arm"])
    for stage in result.stages:
        for strategy in ("current", "bulk-search"):
            arm = stage.arm_report(strategy)
            for basis in ("server", "client"):
                verdict = arm.verdict(basis, plan.threshold_ms)
                if verdict is None:
                    lines.append(f"  {stage.label:<7} {strategy:<10} {basis:<7} no successful samples")
                    continue
                status = "PASS" if verdict.met else "FAIL"
                lines.append(
                    f"  {stage.label:<7} {strategy:<10} {basis:<7} {status}  "
                    f"p90 {verdict.p90_ms:>7.1f} ms  {verdict.fraction_under_threshold:>6.1%} under "
                    f"{plan.threshold_ms:g} ms"
                )

    integrity_status = "PASS" if result.integrity_ok else "FAIL"
    lines.extend(["", f"comparison integrity {integrity_status}"])
    for stage in result.stages:
        lines.append(
            f"  {stage.label:<7} {len(stage.valid_pairs)}/{len(stage.pairs)} valid pairs; "
            f"current-first {stage.order_counts['current_first']}, "
            f"bulk-search-first {stage.order_counts['bulk_search_first']} "
            f"({'balanced' if stage.order_balanced else 'NOT BALANCED'}); "
            f"changed-path current-first {stage.changed_path_order_counts['current_first']}, "
            f"bulk-search-first {stage.changed_path_order_counts['bulk_search_first']} "
            f"({'balanced' if stage.changed_path_order_balanced else 'NOT BALANCED'}); "
            f"semantic mismatches {stage.semantic_mismatches}; "
            f"unresolved {stage.unresolved_identifiers} IDs across {stage.unresolved_pairs} pairs; "
            f"alternative IDs {stage.alternative_identifier_count} across "
            f"{stage.pairs_with_alternative_identifiers}/{len(stage.pairs)} pairs"
        )
    lines.append(f"  request_id round-trip mismatches       {result.request_id_mismatches}")
    lines.append(f"  lookup strategy attribution mismatches {result.lookup_strategy_mismatches}")
    lines.append(f"  semantic response mismatches            {result.semantic_mismatches}")
    lines.append(f"  pairs containing unresolved identifiers {result.unresolved_pairs}")
    lines.append(f"  unresolved identifiers                  {result.unresolved_identifiers}")
    lines.append(f"  incomplete or invalid pairs             {result.invalid_pairs}")

    lines.extend(["", "read this with"])
    lines.extend(f"  - {note}" for note in _comparison_caveats(result))
    return "\n".join(lines)


def render_text(result: BenchmarkResult) -> str:
    """Render a run as an aligned latency table with an SLO verdict per stage."""
    if isinstance(result, ComparisonResult):
        return _render_comparison_text(result)

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
    if result.lookup_strategy_mismatches:
        lines.append(f"lookup strategy attribution mismatches  {result.lookup_strategy_mismatches}")

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
            "so backend caches warm during the run; compare strategies with the same seed and run shape"
        )
    elif plan.workload.unique_ratio >= 1.0 and result.user_model is None:
        notes.append(
            "every identifier is drawn fresh, so this is the cold-cache bound; "
            "re-run with --unique-ratio below 1.0 for the cached case"
        )
    if not plan.workload.uses_identifier_pool and plan.workload.pmid_ratio < 1.0:
        notes.append(
            "the default mixed workload synthesizes PMCID and DOI values that usually report not_found; "
            "they exercise the _msearch miss path but cannot compare source-fetch strategies — use "
            "--identifier-file with real resolving identifiers for that"
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


def render_json(result: BenchmarkResult) -> str:
    return json.dumps(as_dict(result), indent=2)


def _comparison_as_dict(result: ComparisonResult) -> Dict[str, object]:
    plan = result.plan
    return {
        "mode": "paired_lookup_strategy_comparison",
        "target": plan.normalized_base_url,
        "objective": {
            "source": "NCATSTranslator/Core-Components-Working-Group#15",
            "threshold_ms": plan.threshold_ms,
            "quantile": SLO_QUANTILE,
        },
        "workload": {
            "description": _comparison_workload_description(result),
            "batch_size": plan.workload.batch_size,
            "method": plan.workload.normalized_method,
            "lookup_strategies": ["current", "bulk-search"],
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
            "pairs_per_stage": plan.requests,
            "http_requests_per_stage": plan.requests * 2,
            "warmup_pairs": plan.warmup_requests,
            "timeout_seconds": plan.timeout_seconds,
            "stages": list(plan.stages),
            "seed": plan.seed,
            "max_http_concurrency": max(plan.stages),
        },
        "integrity": {
            "valid": result.integrity_ok,
            "request_id_mismatches": result.request_id_mismatches,
            "lookup_strategy_mismatches": result.lookup_strategy_mismatches,
            "semantic_mismatches": result.semantic_mismatches,
            "unresolved_pairs": result.unresolved_pairs,
            "unresolved_identifiers": result.unresolved_identifiers,
            "invalid_pairs": result.invalid_pairs,
        },
        "caveats": _comparison_caveats(result),
        "stages": [_comparison_stage_dict(stage, plan.threshold_ms) for stage in result.stages],
    }


def as_dict(result: BenchmarkResult) -> Dict[str, object]:
    if isinstance(result, ComparisonResult):
        return _comparison_as_dict(result)

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
            "lookup_strategy": plan.workload.lookup_strategy,
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
        "lookup_strategy_mismatches": result.lookup_strategy_mismatches,
        "caveats": _caveats(result),
        "stages": [stage.as_dict(plan.threshold_ms) for stage in result.stages],
    }


def slo_met(result: BenchmarkResult, basis: str) -> bool:
    """Whether every stage met the objective on ``basis``.

    A run with no successful samples or uncertain strategy attribution does not
    count as meeting the objective.  In particular, accepting the latency of
    only the correctly attributed subset would let a mixed/stale deployment
    produce a misleading pass.
    """
    if isinstance(result, ComparisonResult):
        if not result.integrity_ok:
            return False
        verdicts = [
            stage.arm_report(strategy).verdict(basis, result.plan.threshold_ms)
            for stage in result.stages
            for strategy in ("current", "bulk-search")
        ]
        return bool(verdicts) and all(verdict is not None and verdict.met for verdict in verdicts)

    if result.request_id_mismatches or result.lookup_strategy_mismatches:
        return False
    verdicts = [stage.verdict(basis, result.plan.threshold_ms) for stage in result.stages]
    return bool(verdicts) and all(verdict is not None and verdict.met for verdict in verdicts)
