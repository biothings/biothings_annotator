#!/usr/bin/env bash
set -euo pipefail

artifact_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$artifact_dir" rev-parse --show-toplevel)"
result_dir="${PUBLICATIONS_BENCHMARK_RESULT_DIR:-$artifact_dir/reruns}"
base_url="${PUBLICATIONS_BENCHMARK_BASE_URL:-https://annotator.ci.transltr.io}"
mkdir -p "$result_dir"
cd "$repo_root"

run_cell() {
    local mix="$1"
    local seed="$2"
    local corpus="$artifact_dir/corpus-${mix//-/-pmid-}-alt.txt"
    local output="$result_dir/load-${mix}-s${seed}-c8.json"

    printf 'running c=8 mix=%s seed=%s\n' "$mix" "$seed"
    python -m benchmarks.publications \
        --base-url "$base_url" \
        --method POST \
        --batch-size 100 \
        --compare-strategies bulk-search combined-search \
        --identifier-file "$corpus" \
        --concurrency 8 \
        --requests 200 \
        --warmup 20 \
        --seed "$seed" \
        --slo-basis server \
        --json > "$output"
    printf 'completed c=8 mix=%s seed=%s\n' "$mix" "$seed"
}

for mix in 100-0 50-50 0-100; do
    run_cell "$mix" 20260828
done

for mix in 0-100 50-50 100-0; do
    run_cell "$mix" 20260829
done
