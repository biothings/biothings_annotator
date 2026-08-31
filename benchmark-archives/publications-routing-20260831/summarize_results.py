"""Aggregate the retained bulk-search versus combined-search benchmark JSON."""

import json
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path

RESULT_DIR = Path(os.environ.get("PUBLICATIONS_BENCHMARK_RESULT_DIR", Path(__file__).resolve().parent)).resolve()
PRIMARY_PATTERN = re.compile(r"primary-(?P<mix>\d+-\d+)-s(?P<seed>\d+)-c1\.json")
DOI_PATTERN = re.compile(r"doi-confirm-(?P<mix>\d+-\d+)-s(?P<seed>\d+)-c1\.json")
LOAD_PATTERN = re.compile(r"load-(?P<mix>\d+-\d+)-s(?P<seed>\d+)-c(?P<concurrency>\d+)\.json")
ARM_NAMES = ("bulk-search", "combined-search")


def load_runs(pattern: re.Pattern[str]):
    runs = []
    for path in sorted(RESULT_DIR.glob("*.json")):
        match = pattern.fullmatch(path.name)
        if not match:
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        runs.append((path.name, match.groupdict(), report, report["stages"][0]))
    return runs


def distribution(values):
    values = list(values)
    return {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def summarize_group(runs):
    stages = [run[3] for run in runs]
    pairs = sum(stage["pairs"] for stage in stages)
    requested_identifiers = sum(
        stage["arms"]["bulk-search"]["identifiers"]["identifiers_requested"] for stage in stages
    )
    summary = {
        "runs": len(runs),
        "seeds": [int(run[1]["seed"]) for run in runs],
        "pairs": pairs,
        "valid_pairs": sum(stage["valid_pairs"] for stage in stages),
        "changed_path_pairs": sum(stage["changed_path_pairs"] for stage in stages),
        "alternative_identifier_ratio": sum(stage["alternative_identifiers"] for stage in stages)
        / requested_identifiers,
        "arms": {},
        "p90_difference_ms": distribution(stage["p90_difference_ms"]["server"] for stage in stages),
        "paired_median_delta_ms": distribution(stage["paired_delta_ms"]["server"]["all"]["p50_ms"] for stage in stages),
        "bulk_search_first_median_delta_ms": distribution(
            stage["paired_delta_ms"]["server"]["bulk_search_first"]["p50_ms"] for stage in stages
        ),
        "combined_search_first_median_delta_ms": distribution(
            stage["paired_delta_ms"]["server"]["combined_search_first"]["p50_ms"] for stage in stages
        ),
        "combined_search_faster_fraction": distribution(
            stage["paired_delta_ms"]["server"]["all"]["combined_search_faster_fraction"] for stage in stages
        ),
    }
    for arm_name in ARM_NAMES:
        summary["arms"][arm_name] = {
            percentile: distribution(stage["arms"][arm_name]["server_latency"][percentile] for stage in stages)
            for percentile in ("p50_ms", "p90_ms", "p99_ms")
        }
    return summary


def compact_run(filename, metadata, report, stage):
    return {
        "file": filename,
        "mix": metadata["mix"],
        "seed": int(metadata["seed"]),
        "concurrency": stage["concurrency"],
        "pairs": stage["pairs"],
        "valid_pairs": stage["valid_pairs"],
        "changed_path_pairs": stage["changed_path_pairs"],
        "bulk_search_p90_ms": stage["arms"]["bulk-search"]["server_latency"]["p90_ms"],
        "combined_search_p90_ms": stage["arms"]["combined-search"]["server_latency"]["p90_ms"],
        "p90_difference_ms": stage["p90_difference_ms"]["server"],
        "paired_median_delta_ms": stage["paired_delta_ms"]["server"]["all"]["p50_ms"],
        "bulk_search_first_median_delta_ms": stage["paired_delta_ms"]["server"]["bulk_search_first"]["p50_ms"],
        "combined_search_first_median_delta_ms": stage["paired_delta_ms"]["server"]["combined_search_first"]["p50_ms"],
        "combined_search_faster_fraction": stage["paired_delta_ms"]["server"]["all"]["combined_search_faster_fraction"],
        "integrity": report["integrity"],
    }


def main():
    primary_runs = load_runs(PRIMARY_PATTERN)
    doi_runs = load_runs(DOI_PATTERN)
    load_runs_list = load_runs(LOAD_PATTERN)
    primary_groups = defaultdict(list)
    for run in primary_runs:
        primary_groups[run[1]["mix"]].append(run)

    full_runs = primary_runs + doi_runs + load_runs_list
    integrity_keys = (
        "request_id_mismatches",
        "lookup_strategy_mismatches",
        "lookup_fallback_samples",
        "lookup_fallback_attribution_missing",
        "semantic_mismatches",
        "unresolved_pairs",
        "unresolved_identifiers",
        "invalid_pairs",
    )
    summary = {
        "strategies": ["bulk-search", "combined-search"],
        "delta_meaning": "combined-search minus bulk-search; negative favors combined-search",
        "full_cells": len(full_runs),
        "measured_pairs": sum(run[3]["pairs"] for run in full_runs),
        "measured_http_requests": 2 * sum(run[3]["pairs"] for run in full_runs),
        "warmup_pairs": sum(run[2]["load"]["warmup_pairs"] for run in full_runs),
        "total_http_requests_including_warmup": 2
        * sum(run[3]["pairs"] + run[2]["load"]["warmup_pairs"] for run in full_runs),
        "valid_pairs": sum(run[3]["valid_pairs"] for run in full_runs),
        "integrity_totals": {key: sum(run[2]["integrity"][key] for run in full_runs) for key in integrity_keys},
        "primary_c1": {mix: summarize_group(runs) for mix, runs in sorted(primary_groups.items(), reverse=True)},
        "doi_confirmation_c1": [compact_run(*run) for run in doi_runs],
        "moderate_load": [compact_run(*run) for run in load_runs_list],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
