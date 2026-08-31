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
    local output="$result_dir/primary-${mix}-s${seed}-c1.json"

    if [[ "$mix" == "100-0" ]]; then
        corpus="$artifact_dir/corpus-100-pmid-0-alt.txt"
    fi

    printf 'running primary mix=%s seed=%s\n' "$mix" "$seed"
    python -m benchmarks.publications \
        --base-url "$base_url" \
        --method POST \
        --batch-size 100 \
        --compare-strategies bulk-search combined-search \
        --identifier-file "$corpus" \
        --concurrency 1 \
        --requests 200 \
        --warmup 20 \
        --seed "$seed" \
        --slo-basis server \
        --json > "$output"
    printf 'completed primary mix=%s seed=%s\n' "$mix" "$seed"
}

# Rotate the mix order between seeds to reduce correlation with shared-CI drift.
for mix in 100-0 75-25 50-50 25-75 0-100; do
    run_cell "$mix" 20260828
done

for mix in 0-100 25-75 50-50 75-25 100-0; do
    run_cell "$mix" 20260829
done

for mix in 50-50 100-0 0-100 75-25 25-75; do
    run_cell "$mix" 20260830
done
