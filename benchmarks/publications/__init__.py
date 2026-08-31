"""Load benchmark for the ``/publications`` endpoint.

``/publications`` is intended as a drop-in replacement for DocumentMetadataAPI,
whose specification (NCATSTranslator/Core-Components-Working-Group#15) sets a
p90 latency objective of 150 ms for requests carrying up to 100 publication
identifiers. This package measures a deployment against that objective.

Run it from the repository root:

    python -m benchmarks.publications --help
"""

from benchmarks.publications.corpus import CorpusConfig, IdentifierCorpus, load_identifier_file
from benchmarks.publications.metrics import (
    SLO_QUANTILE,
    SLO_THRESHOLD_MS,
    LatencySummary,
    Sample,
    SloVerdict,
    StageReport,
    percentile,
)
from benchmarks.publications.report import as_dict, render_json, render_text, slo_met
from benchmarks.publications.runner import (
    ComparisonResult,
    ComparisonStage,
    PairedObservation,
    RunResult,
    run_comparison_plan,
    run_plan,
    verify_pmid_pool,
)
from benchmarks.publications.users import UserModel, capacity_table, run_user_plan, supported_users
from benchmarks.publications.workload import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_COMPARISON_STRATEGIES,
    DEFAULT_LOOKUP_STRATEGY,
    LOOKUP_STRATEGY_HEADER,
    SUPPORTED_LOOKUP_STRATEGIES,
    RunPlan,
    Workload,
)

__all__ = [
    "CorpusConfig",
    "ComparisonResult",
    "ComparisonStage",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_COMPARISON_STRATEGIES",
    "DEFAULT_LOOKUP_STRATEGY",
    "IdentifierCorpus",
    "LatencySummary",
    "LOOKUP_STRATEGY_HEADER",
    "RunPlan",
    "RunResult",
    "SLO_QUANTILE",
    "SLO_THRESHOLD_MS",
    "Sample",
    "PairedObservation",
    "SloVerdict",
    "StageReport",
    "SUPPORTED_LOOKUP_STRATEGIES",
    "UserModel",
    "Workload",
    "as_dict",
    "capacity_table",
    "load_identifier_file",
    "percentile",
    "render_json",
    "render_text",
    "run_comparison_plan",
    "run_plan",
    "run_user_plan",
    "slo_met",
    "supported_users",
    "verify_pmid_pool",
]
