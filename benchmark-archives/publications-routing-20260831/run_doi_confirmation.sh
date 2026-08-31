#!/usr/bin/env bash
set -euo pipefail

artifact_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$artifact_dir" rev-parse --show-toplevel)"
result_dir="${PUBLICATIONS_BENCHMARK_RESULT_DIR:-$artifact_dir/reruns}"
base_url="${PUBLICATIONS_BENCHMARK_BASE_URL:-https://annotator.ci.transltr.io}"
mkdir -p "$result_dir"
cd "$repo_root"

for mix in 75-25 50-50 25-75 0-100; do
    corpus="$artifact_dir/corpus-doi-${mix//-/-pmid-}-doi.txt"
    output="$result_dir/doi-confirm-${mix}-s20260831-c1.json"
    printf 'running DOI confirmation mix=%s\n' "$mix"
    python -m benchmarks.publications \
        --base-url "$base_url" \
        --method POST \
        --batch-size 100 \
        --compare-strategies bulk-search combined-search \
        --identifier-file "$corpus" \
        --concurrency 1 \
        --requests 200 \
        --warmup 20 \
        --seed 20260831 \
        --slo-basis server \
        --json > "$output"
    printf 'completed DOI confirmation mix=%s\n' "$mix"
done
