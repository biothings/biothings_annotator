"""Latency accounting and SLO evaluation for the ``/publications`` benchmark.

CCWG#15 states the objective two ways: "SLO for p90 should be 150ms" and "90% of
requests should take <150ms". Those are the same intent but not the same
arithmetic, so both are reported. The pass/fail verdict uses the second form --
the fraction of requests strictly under the threshold -- because it is a direct
count that needs no interpolation convention to be reproducible. The p90 value
is reported alongside it because it is what the objective is usually quoted as.

Every sample carries two latencies. ``client_ms`` is wall-clock time from
request start to response fully read, which is what a UI experiences.
``server_ms`` is the endpoint's own ``_meta.processing_time_ms``. Their
difference is network transit, TLS framing, and response transfer, none of which
the service controls and all of which depend on where the harness runs. Keeping
both is what makes a run from a laptop interpretable at all: a client-side miss
with a comfortable server-side margin is a vantage-point artifact, while a
server-side miss is a real regression from any vantage point.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# CCWG#15: "SLO for p90 should be 150ms for a good user experience".
SLO_THRESHOLD_MS = 150.0
SLO_QUANTILE = 0.90


@dataclass(frozen=True)
class Sample:
    """One completed (or failed) request."""

    client_ms: float
    status: Optional[int] = None
    server_ms: Optional[int] = None
    requested: int = 0
    found: int = 0
    not_found: int = 0
    response_bytes: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200


def percentile(values: Sequence[float], quantile: float) -> float:
    """Nearest-rank percentile: the smallest sample at or above the quantile.

    Nearest-rank is used rather than an interpolating definition because an
    interpolated p90 reports a latency that was never observed. For an SLO
    check, an observed value is the defensible one.
    """
    if not values:
        raise ValueError("percentile of an empty sample set is undefined")
    if not 0.0 < quantile <= 1.0:
        raise ValueError("quantile must be within (0.0, 1.0]")
    ordered = sorted(values)
    rank = math.ceil(quantile * len(ordered))
    return ordered[max(rank, 1) - 1]


@dataclass(frozen=True)
class LatencySummary:
    """Distribution of one latency series, in milliseconds."""

    count: int
    minimum: float
    p50: float
    p90: float
    p95: float
    p99: float
    maximum: float
    mean: float

    @classmethod
    def from_values(cls, values: Sequence[float]) -> Optional["LatencySummary"]:
        """Summarize ``values``, or return ``None`` when there is nothing to summarize."""
        if not values:
            return None
        return cls(
            count=len(values),
            minimum=min(values),
            p50=percentile(values, 0.50),
            p90=percentile(values, 0.90),
            p95=percentile(values, 0.95),
            p99=percentile(values, 0.99),
            maximum=max(values),
            mean=sum(values) / len(values),
        )

    def as_dict(self) -> Dict[str, float]:
        return {
            "count": self.count,
            "min_ms": round(self.minimum, 2),
            "p50_ms": round(self.p50, 2),
            "p90_ms": round(self.p90, 2),
            "p95_ms": round(self.p95, 2),
            "p99_ms": round(self.p99, 2),
            "max_ms": round(self.maximum, 2),
            "mean_ms": round(self.mean, 2),
        }


@dataclass(frozen=True)
class SloVerdict:
    """Whether one latency series meets the CCWG#15 objective."""

    basis: str
    threshold_ms: float
    quantile: float
    p90_ms: float
    fraction_under_threshold: float
    sample_count: int

    @property
    def met(self) -> bool:
        return self.fraction_under_threshold >= self.quantile

    @property
    def headroom_ms(self) -> float:
        """Distance from the p90 to the threshold; negative means over budget."""
        return self.threshold_ms - self.p90_ms

    @classmethod
    def evaluate(
        cls,
        values: Sequence[float],
        basis: str,
        threshold_ms: float = SLO_THRESHOLD_MS,
        quantile: float = SLO_QUANTILE,
    ) -> Optional["SloVerdict"]:
        if not values:
            return None
        under = sum(1 for value in values if value < threshold_ms)
        return cls(
            basis=basis,
            threshold_ms=threshold_ms,
            quantile=quantile,
            p90_ms=percentile(values, quantile),
            fraction_under_threshold=under / len(values),
            sample_count=len(values),
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "basis": self.basis,
            "met": self.met,
            "threshold_ms": self.threshold_ms,
            "quantile": self.quantile,
            "p90_ms": round(self.p90_ms, 2),
            "fraction_under_threshold": round(self.fraction_under_threshold, 4),
            "headroom_ms": round(self.headroom_ms, 2),
            "sample_count": self.sample_count,
        }


@dataclass
class StageReport:
    """Aggregated results for one measured stage of a run."""

    label: str
    concurrency: int
    wall_seconds: float
    samples: List[Sample] = field(default_factory=list)
    # Set when the corpus was verified before measuring, which primes the
    # backend cache and makes the stage optimistic by construction.
    cache_primed: bool = False

    @property
    def successful(self) -> List[Sample]:
        return [sample for sample in self.samples if sample.ok]

    @property
    def status_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for sample in self.samples:
            key = sample.error if sample.error else str(sample.status)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def throughput_rps(self) -> float:
        if self.wall_seconds <= 0:
            return 0.0
        return len(self.samples) / self.wall_seconds

    def client_latency(self) -> Optional[LatencySummary]:
        return LatencySummary.from_values([sample.client_ms for sample in self.successful])

    def server_latency(self) -> Optional[LatencySummary]:
        return LatencySummary.from_values(
            [float(sample.server_ms) for sample in self.successful if sample.server_ms is not None]
        )

    def overhead_latency(self) -> Optional[LatencySummary]:
        """Per-sample ``client_ms - server_ms``: transit plus transfer."""
        return LatencySummary.from_values(
            [
                max(sample.client_ms - float(sample.server_ms), 0.0)
                for sample in self.successful
                if sample.server_ms is not None
            ]
        )

    def verdict(self, basis: str, threshold_ms: float = SLO_THRESHOLD_MS) -> Optional[SloVerdict]:
        if basis == "client":
            values = [sample.client_ms for sample in self.successful]
        elif basis == "server":
            values = [float(sample.server_ms) for sample in self.successful if sample.server_ms is not None]
        else:
            raise ValueError("basis must be 'client' or 'server'")
        return SloVerdict.evaluate(values, basis=basis, threshold_ms=threshold_ms)

    @property
    def identifier_stats(self) -> Dict[str, object]:
        """How populated the measured responses were.

        A batch of randomly drawn PMIDs is not guaranteed to resolve, and an
        all-``not_found`` response is cheap to serve, so a benchmark that did not
        report its own hit ratio could report a passing latency for work the
        service never did.
        """
        successful = self.successful
        if not successful:
            return {"requests": 0}
        requested = sum(sample.requested for sample in successful)
        found = sum(sample.found for sample in successful)
        return {
            "requests": len(successful),
            "identifiers_requested": requested,
            "identifiers_found": found,
            "found_ratio": round(found / requested, 4) if requested else 0.0,
            "mean_batch_size": round(requested / len(successful), 2),
            "mean_response_kb": round(sum(sample.response_bytes for sample in successful) / len(successful) / 1024, 1),
        }

    def as_dict(self, threshold_ms: float = SLO_THRESHOLD_MS) -> Dict[str, object]:
        client = self.client_latency()
        server = self.server_latency()
        overhead = self.overhead_latency()
        client_verdict = self.verdict("client", threshold_ms)
        server_verdict = self.verdict("server", threshold_ms)
        return {
            "label": self.label,
            "concurrency": self.concurrency,
            "wall_seconds": round(self.wall_seconds, 3),
            "requests": len(self.samples),
            "successful": len(self.successful),
            "throughput_rps": round(self.throughput_rps, 2),
            "status_counts": self.status_counts,
            "cache_primed": self.cache_primed,
            "identifiers": self.identifier_stats,
            "client_latency": client.as_dict() if client else None,
            "server_latency": server.as_dict() if server else None,
            "network_overhead": overhead.as_dict() if overhead else None,
            "slo": {
                "client": client_verdict.as_dict() if client_verdict else None,
                "server": server_verdict.as_dict() if server_verdict else None,
            },
        }
