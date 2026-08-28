"""Identifier corpora for the ``/publications`` benchmark.

The workload's identifiers decide what the benchmark actually measures, so the
sampling strategy is part of the methodology rather than an implementation
detail.

PMIDs are drawn at random from the numeric range PubMed has issued. Roughly 98%
of that range resolves against the deployed index, so an unverified random draw
already produces a near-fully-populated response while keeping every lookup a
first-time lookup. That matters more than a perfect hit ratio: the backend
caches, so any identifier the harness has already queried answers from a warm
cache and reports a latency the next real user would not see. Verification is
therefore opt-in (:func:`verify_pmid_pool`) and the report labels the run as
cache-primed when it is used.

PMCIDs and DOIs are synthesized by the default mixed workload. Because those
values usually miss, a benchmark comparing implementations should instead load
a curated file of known-resolving PMIDs, PMCIDs, and DOIs. A fixed pool is
sampled without replacement within each request and with the same seeded random
generator as the synthetic corpus, so two runs with the same seed issue the
same batches.
"""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Union

# PubMed had issued IDs up to roughly 41,000,000 by 2026. The default upper
# bound stays below that so the draw does not concentrate on the newest records,
# which are the least likely to be present in an index snapshot.
DEFAULT_MAX_PMID = 38_000_000
DEFAULT_MIN_PMID = 1


def load_identifier_file(path: Union[str, Path]) -> List[str]:
    """Load one publication identifier per line from ``path``.

    Blank lines and lines whose first non-whitespace character is ``#`` are
    ignored. Identifiers are stripped and deduplicated while preserving their
    first-seen order; inline ``#`` characters remain part of an identifier
    because they are legal in DOI suffixes.
    """
    identifiers: List[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        identifier = line.strip()
        if not identifier or identifier.startswith("#"):
            continue
        identifiers.append(identifier)
    return list(dict.fromkeys(identifiers))


@dataclass(frozen=True)
class CorpusConfig:
    """How to draw identifiers for a run."""

    min_pmid: int = DEFAULT_MIN_PMID
    max_pmid: int = DEFAULT_MAX_PMID
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        if self.min_pmid < 1:
            raise ValueError("min_pmid must be >= 1; PMID:0 is not a valid identifier")
        if self.max_pmid < self.min_pmid:
            raise ValueError("max_pmid must be >= min_pmid")


class IdentifierCorpus:
    """Draw PMID, PMCID, and DOI identifiers for benchmark batches.

    Instances are not thread-safe and are not safe to share across concurrent
    workers: they own a single :class:`random.Random`. The runner gives each
    worker its own corpus, which makes each worker's draw sequence reproducible.
    Aggregate single-arm assignment can still vary when faster workers claim
    more requests; paired comparison mode therefore precomputes every batch
    before any timed request starts.
    """

    def __init__(
        self,
        config: Optional[CorpusConfig] = None,
        hot_pool: Optional[Sequence[str]] = None,
        identifier_pool: Optional[Sequence[str]] = None,
    ):
        self.config = config or CorpusConfig()
        self._random = random.Random(self.config.seed)
        self._hot_pool = list(hot_pool or [])
        self._identifier_pool = list(dict.fromkeys(identifier_pool or []))
        self._catalog: List[str] = []
        self._catalog_cumulative_weights: List[float] = []

    @property
    def hot_pool(self) -> List[str]:
        """Identifiers reused across batches to exercise a warm backend cache."""
        return list(self._hot_pool)

    @property
    def identifier_pool(self) -> List[str]:
        """The fixed real-identifier pool, in first-seen input order."""
        return list(self._identifier_pool)

    def fresh_pmid(self) -> str:
        return f"PMID:{self._random.randint(self.config.min_pmid, self.config.max_pmid)}"

    def fresh_pmcid(self) -> str:
        """A PMCID in PubMed's doubled form, which is what the index stores."""
        return f"PMC:PMC{self._random.randint(1, 9_000_000)}"

    def fresh_doi(self) -> str:
        registrant = self._random.randint(1000, 9999)
        suffix = self._random.randint(100_000, 999_999)
        return f"doi:10.{registrant}/bench.{suffix}"

    def seed_hot_pool(self, size: int) -> List[str]:
        """Fill the reusable pool with fresh PMIDs and return it."""
        if size < 0:
            raise ValueError("hot pool size must be >= 0")
        self._hot_pool = [self.fresh_pmid() for _ in range(size)]
        return self.hot_pool

    def seed_catalog(self, size: int, zipf_exponent: float = 1.0) -> List[str]:
        """Build a shared catalogue of papers with a skewed popularity ranking.

        This is what a *population* of users looks like, as distinct from one
        user issuing back-to-back requests. Real readers do not draw papers
        uniformly: a small number of publications are requested constantly and a
        long tail almost never, which is the distribution that decides how much
        of the population's traffic a backend cache can absorb. Drawing the
        catalogue uniformly would understate cache hits; replaying one fixed
        batch would overstate them.

        ``zipf_exponent`` is the skew. 0.0 is uniform; 1.0 is classic Zipf,
        where the most popular paper is drawn about twice as often as the second
        and a hundred times as often as the hundredth.
        """
        if size < 1:
            raise ValueError("catalogue size must be >= 1")
        if zipf_exponent < 0:
            raise ValueError("zipf_exponent must be >= 0")

        return self.seed_catalog_from_identifiers(
            [self.fresh_pmid() for _ in range(size)],
            zipf_exponent,
        )

    def seed_catalog_from_identifiers(
        self,
        identifiers: Sequence[str],
        zipf_exponent: float = 1.0,
    ) -> List[str]:
        """Use a fixed identifier pool as the popularity-ranked user catalogue."""
        if zipf_exponent < 0:
            raise ValueError("zipf_exponent must be >= 0")
        self._catalog = list(dict.fromkeys(identifiers))
        if not self._catalog:
            raise ValueError("catalogue identifiers must not be empty")

        # Cumulative weights are precomputed once so each draw is a binary
        # search rather than a rebuild of the whole weight vector.
        cumulative = 0.0
        self._catalog_cumulative_weights = []
        for rank in range(1, len(self._catalog) + 1):
            cumulative += 1.0 / (rank**zipf_exponent)
            self._catalog_cumulative_weights.append(cumulative)
        return list(self._catalog)

    @property
    def catalog(self) -> List[str]:
        """The shared, popularity-ranked pool a user population draws from."""
        return list(self._catalog)

    def catalog_batch(self, size: int) -> List[str]:
        """Draw one user's request from the shared catalogue by popularity.

        Deduplicated like :meth:`batch`, which under a skewed draw is a real
        effect rather than a rounding detail: a popular paper drawn twice in one
        request collapses to a single lookup, exactly as the endpoint would
        collapse it.
        """
        if size < 1:
            raise ValueError("batch size must be >= 1")
        if not self._catalog:
            raise ValueError("seed_catalog must be called before drawing catalogue batches")
        drawn = self._random.choices(
            self._catalog,
            cum_weights=self._catalog_cumulative_weights,
            k=size,
        )
        return list(dict.fromkeys(drawn))

    def pool_batch(self, size: int) -> List[str]:
        """Sample a full, duplicate-free request from the fixed identifier pool."""
        if size < 1:
            raise ValueError("batch size must be >= 1")
        if len(self._identifier_pool) < size:
            raise ValueError(f"identifier pool has {len(self._identifier_pool)} entries but batch size is {size}")
        return self._random.sample(self._identifier_pool, size)

    def batch(self, size: int, pmid_ratio: float = 1.0, unique_ratio: float = 1.0) -> List[str]:
        """Build one request's identifier list.

        ``pmid_ratio`` splits the batch between the batched ``_mget`` path
        (PMID) and the per-identifier ``_msearch`` path (PMCID and DOI, drawn in
        alternation). ``unique_ratio`` splits it between fresh identifiers and
        the hot pool, which is how a cold-cache run is told from a warm-cache
        one.

        The returned list is deduplicated, because the endpoint deduplicates
        before querying the backend and returning near-duplicate batches would
        overstate the work performed. Deduplication can leave the batch shorter
        than ``size``; the report records the sizes actually sent.
        """
        if size < 1:
            raise ValueError("batch size must be >= 1")
        if not 0.0 <= pmid_ratio <= 1.0:
            raise ValueError("pmid_ratio must be within [0.0, 1.0]")
        if not 0.0 <= unique_ratio <= 1.0:
            raise ValueError("unique_ratio must be within [0.0, 1.0]")

        identifiers: List[str] = []
        # round() rather than int(): int() truncates, so a 100-identifier batch
        # at unique_ratio=0.999 would silently reuse one identifier from the hot
        # pool. round() keeps the split faithful to the requested ratio.
        reused_count = size - round(size * unique_ratio)
        if reused_count and not self._hot_pool:
            raise ValueError("unique_ratio below 1.0 requires a seeded hot pool")

        for position in range(size):
            if position < reused_count:
                identifiers.append(self._random.choice(self._hot_pool))
                continue
            if self._random.random() < pmid_ratio:
                identifiers.append(self.fresh_pmid())
            elif position % 2:
                identifiers.append(self.fresh_pmcid())
            else:
                identifiers.append(self.fresh_doi())

        # dict.fromkeys keeps first-seen order, so a seeded run stays stable.
        return list(dict.fromkeys(identifiers))
