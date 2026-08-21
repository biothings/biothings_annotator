"""Load benchmark for the ``/publications`` endpoint.

``/publications`` is intended as a drop-in replacement for DocumentMetadataAPI,
whose specification (NCATSTranslator/Core-Components-Working-Group#15) sets a
p90 latency objective of 150 ms for requests carrying up to 100 publication
identifiers. This package measures a deployment against that objective.

Run it from the repository root:

    python -m benchmarks.publications --help
"""

from benchmarks.publications.corpus import CorpusConfig, IdentifierCorpus
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
from benchmarks.publications.runner import RunResult, run_plan, verify_pmid_pool
from benchmarks.publications.users import UserModel, capacity_table, run_user_plan, supported_users
from benchmarks.publications.workload import DEFAULT_BATCH_SIZE, RunPlan, Workload

__all__ = [
    "CorpusConfig",
    "DEFAULT_BATCH_SIZE",
    "IdentifierCorpus",
    "LatencySummary",
    "RunPlan",
    "RunResult",
    "SLO_QUANTILE",
    "SLO_THRESHOLD_MS",
    "Sample",
    "SloVerdict",
    "StageReport",
    "UserModel",
    "Workload",
    "as_dict",
    "capacity_table",
    "percentile",
    "render_json",
    "render_text",
    "run_plan",
    "run_user_plan",
    "slo_met",
    "supported_users",
    "verify_pmid_pool",
]
