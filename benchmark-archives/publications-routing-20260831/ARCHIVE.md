# Publications routing benchmark archive

This directory preserves the bulk-search versus combined-search experiment run against
`https://annotator.ci.transltr.io` on 2026-08-31.

- Deployed revision: `82d3accf6c219860583d3b9b91029538b6a434a1`
- Measurement window: 2026-08-31 19:57:53–20:12:21 UTC
- Primary metric: endpoint `_meta.processing_time_ms`
- Raw pair observations were not retained; the JSON files contain aggregate harness reports.

The archive commit inherits the exact benchmark harness and temporary server selectors used for the
experiment. To inspect or rerun it:

```shell
git switch --detach benchmark-publications-routing-20260831
python -m pytest -q tests/test_publications_load.py -m unit
bash benchmark-archives/publications-routing-20260831/run_primary.sh
```

Rerun output defaults to the ignored `reruns/` directory. Override the destination or target without
editing the retained scripts:

```shell
PUBLICATIONS_BENCHMARK_RESULT_DIR=/path/to/results \
PUBLICATIONS_BENCHMARK_BASE_URL=https://annotator.ci.transltr.io \
bash benchmark-archives/publications-routing-20260831/run_primary.sh
```

Generate a summary for a rerun with:

```shell
PUBLICATIONS_BENCHMARK_RESULT_DIR=/path/to/results \
python benchmark-archives/publications-routing-20260831/summarize_results.py
```

Run `shasum -a 256 -c manifest.sha256` from this directory to verify the retained artifacts.
