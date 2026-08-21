"""Rendering for ``/publications`` benchmark results."""

import json
from typing import Dict, List, Optional

from benchmarks.publications.metrics import SLO_QUANTILE, LatencySummary, StageReport
from benchmarks.publications.runner import RunResult

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


def render_text(result: RunResult) -> str:
    """Render a run as an aligned latency table with an SLO verdict per stage."""
    plan = result.plan
    threshold = plan.threshold_ms
    lines = [
        "/publications load benchmark",
        f"  target     {plan.normalized_base_url}",
        f"  workload   {plan.workload.describe()}",
        f"  load       {plan.requests} measured requests per stage, "
        f"{plan.warmup_requests} discarded warmup, {plan.timeout_seconds:g}s timeout",
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
            lines.append(
                f"  {stage.label:<7} {basis:<7} {status}  "
                f"p90 {verdict.p90_ms:>7.1f} ms  "
                f"{verdict.fraction_under_threshold:>6.1%} under {threshold:g} ms  "
                f"headroom {verdict.headroom_ms:>+8.1f} ms"
            )

    failures = {
        status: count for stage in result.stages for status, count in stage.status_counts.items() if status != "200"
    }
    if failures:
        lines.extend(["", f"non-200 and transport failures  {failures}"])
    if result.request_id_mismatches:
        lines.append(f"request_id round-trip mismatches  {result.request_id_mismatches}")

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
    if plan.workload.unique_ratio >= 1.0:
        notes.append(
            "every identifier is drawn fresh, so this is the cold-cache bound; "
            "re-run with --unique-ratio below 1.0 for the cached case"
        )
    if plan.workload.pmid_ratio < 1.0:
        notes.append(
            "PMCID and DOI identifiers report not_found until the index carries pubmed.identifiers, "
            "but they still take the per-identifier _msearch path this run is measuring"
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
            "pmid_ratio": plan.workload.pmid_ratio,
            "unique_ratio": plan.workload.unique_ratio,
        },
        "load": {
            "requests_per_stage": plan.requests,
            "warmup_requests": plan.warmup_requests,
            "timeout_seconds": plan.timeout_seconds,
            "stages": list(plan.stages),
            "seed": plan.seed,
        },
        "request_id_mismatches": result.request_id_mismatches,
        "caveats": _caveats(result),
        "stages": [stage.as_dict(plan.threshold_ms) for stage in result.stages],
    }


def slo_met(result: RunResult, basis: str) -> bool:
    """Whether every stage met the objective on ``basis``.

    A run with no successful samples does not count as meeting the objective.
    """
    verdicts = [stage.verdict(basis, result.plan.threshold_ms) for stage in result.stages]
    return bool(verdicts) and all(verdict is not None and verdict.met for verdict in verdicts)
