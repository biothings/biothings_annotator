"""Workload shapes for the ``/publications`` benchmark.

A workload is the part of the run that decides what the service is asked to do:
how many identifiers per request, of which kinds, how often they repeat, and over
which transport. The run plan wraps that with how hard to push it.
"""

import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from benchmarks.publications.corpus import CorpusConfig, IdentifierCorpus
from benchmarks.publications.metrics import SLO_THRESHOLD_MS

PUBLICATIONS_PATH = "/publications"
# CCWG#15: "Expect up to 100 pubids in request". This is the headline case, so it
# is the default batch size rather than something the caller has to opt into.
DEFAULT_BATCH_SIZE = 100
SUPPORTED_METHODS = ("GET", "POST")


@dataclass(frozen=True)
class Workload:
    """What a single request looks like."""

    batch_size: int = DEFAULT_BATCH_SIZE
    method: str = "GET"
    # Fraction of each batch drawn as PMIDs. PMIDs resolve through one batched
    # _mget; PMCIDs and DOIs are grouped into one bulk _search, so lowering this
    # exercises more of the alternative-identifier lookup path.
    pmid_ratio: float = 1.0
    # Fraction of each batch drawn fresh. 1.0 keeps every lookup a first-time
    # lookup (cold backend cache, the pessimistic bound); lowering it replays
    # identifiers from the hot pool (warm cache, the optimistic bound).
    unique_ratio: float = 1.0
    hot_pool_size: int = 1_000
    # Optional curated real identifiers. When present this replaces synthesized
    # and hot-pool sampling entirely, allowing repeatable resolving batches
    # under the same seed.
    identifier_pool: Tuple[str, ...] = ()
    identifier_pool_source: Optional[str] = None

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 100:
            raise ValueError("batch_size must be within 1..100; CCWG#15 caps a request at 100 identifiers")
        if self.method.upper() not in SUPPORTED_METHODS:
            raise ValueError(f"method must be one of {SUPPORTED_METHODS}")
        if not 0.0 <= self.pmid_ratio <= 1.0:
            raise ValueError("pmid_ratio must be within [0.0, 1.0]")
        if not 0.0 <= self.unique_ratio <= 1.0:
            raise ValueError("unique_ratio must be within [0.0, 1.0]")
        if self.unique_ratio < 1.0 and self.hot_pool_size < 1:
            raise ValueError("a hot pool is required when unique_ratio is below 1.0")
        normalized_pool = tuple(dict.fromkeys(self.identifier_pool))
        object.__setattr__(self, "identifier_pool", normalized_pool)
        if normalized_pool and len(normalized_pool) < self.batch_size:
            raise ValueError(
                f"identifier pool has {len(normalized_pool)} unique entries but batch size is {self.batch_size}"
            )
        if self.identifier_pool_source and not normalized_pool:
            raise ValueError("identifier_pool_source requires a non-empty identifier_pool")

    @property
    def normalized_method(self) -> str:
        return self.method.upper()

    @property
    def uses_identifier_pool(self) -> bool:
        return bool(self.identifier_pool)

    def describe(self) -> str:
        parts = [f"{self.batch_size} ids", self.normalized_method]
        if self.uses_identifier_pool:
            source = self.identifier_pool_source or "provided pool"
            parts.append(f"{len(self.identifier_pool)} real ids from {source}")
        elif self.pmid_ratio >= 1.0:
            parts.append("PMID only")
        else:
            parts.append(f"{self.pmid_ratio:.0%} PMID / {1 - self.pmid_ratio:.0%} PMC+DOI")
        if not self.uses_identifier_pool:
            parts.append("cold cache" if self.unique_ratio >= 1.0 else f"{1 - self.unique_ratio:.0%} replayed")
        return ", ".join(parts)

    def build_corpus(self, seed: Optional[int]) -> IdentifierCorpus:
        corpus = IdentifierCorpus(CorpusConfig(seed=seed), identifier_pool=self.identifier_pool)
        if not self.uses_identifier_pool and self.unique_ratio < 1.0:
            corpus.seed_hot_pool(self.hot_pool_size)
        return corpus

    def next_batch(self, corpus: IdentifierCorpus) -> List[str]:
        if self.uses_identifier_pool:
            return corpus.pool_batch(self.batch_size)
        return corpus.batch(
            size=self.batch_size,
            pmid_ratio=self.pmid_ratio,
            unique_ratio=self.unique_ratio,
        )

    def build_request(self, identifiers: List[str], request_id: str) -> Tuple[str, Dict[str, object]]:
        """Return the request path and the httpx keyword arguments for one call.

        GET uses the legacy comma-separated ``pubids`` form that
        DocumentMetadataAPI clients send today. POST uses the JSON body, which is
        the only form able to carry a DOI whose suffix contains a comma.
        """
        if self.normalized_method == "GET":
            query = urllib.parse.urlencode({"pubids": ",".join(identifiers), "request_id": request_id})
            return f"{PUBLICATIONS_PATH}?{query}", {}
        return PUBLICATIONS_PATH, {"json": {"ids": identifiers, "request_id": request_id}}


@dataclass(frozen=True)
class RunPlan:
    """How hard to push a workload, and against what."""

    base_url: str
    workload: Workload
    concurrency: int = 1
    requests: int = 100
    warmup_requests: int = 10
    timeout_seconds: float = 30.0
    seed: Optional[int] = None
    threshold_ms: float = SLO_THRESHOLD_MS
    # Concurrency levels for a load-bearing sweep. Empty means a single stage at
    # ``concurrency``.
    ramp: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("base_url is required")
        if self.concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if self.requests < 1:
            raise ValueError("requests must be >= 1")
        if self.warmup_requests < 0:
            raise ValueError("warmup_requests must be >= 0")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.threshold_ms <= 0:
            raise ValueError("threshold_ms must be greater than zero")
        if any(level < 1 for level in self.ramp):
            raise ValueError("every ramp level must be >= 1")

    @property
    def stages(self) -> Tuple[int, ...]:
        return self.ramp or (self.concurrency,)

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")
