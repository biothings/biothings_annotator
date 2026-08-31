# Publications lookup-strategy A/B — CI, 2026-08-31

## Decision

**Do not adopt `combined-search`, and do not add adaptive routing for it. Keep `bulk-search`.**

For every mixed PMID/alternative-ID workload, `combined-search` increased handler time. Across three
replicated c=1 runs, its paired median penalty was 5–6 ms at 75/25, 10–11 ms at 50/50, and 5–6 ms at
25/75. Both request-order strata agreed in every run. A DOI-only confirmation reproduced the direction,
and the 50/50 penalty persisted at c=4 and c=8.

Neither endpoint offered a useful adaptive branch. With all alternative IDs, `combined-search`
deliberately executes the same bulk-search code and the paired median was 0 ms. With all PMIDs, marginal
p90 differed by only 1–2 ms at c=1—comparable to the 1 ms apparent difference in the identical-code
control—while paired medians were consistently +1 ms (combined slower). At c=4 the all-PMID p90s tied;
at c=8 their direction changed between seeds. That is a tie/noise result, not a demonstrated niche for
combined search.

Taken with the earlier current-versus-bulk A/B, the best measured strategy remains the concurrent PMID
`_mget` plus one bulk alternative-ID `_search`.

## Deployment gate

- Target: `https://annotator.ci.transltr.io`
- Deployed revision: `82d3accf6c219860583d3b9b91029538b6a434a1` (PR #94 merge commit)
- Backend: `elasticsearch`, connection `in_cluster`
- Cache-busted `/version/` and `/status/` checks matched before and after the run.
- `/status/` returned `{"success":true}` at both gates.
- Measurement window, including preflight: 2026-08-31 19:57:53–20:12:21 UTC.

## Test design

- Explicit pair: `bulk-search` control versus `combined-search` experiment.
- POST requests carrying 100 real, resolving identifiers.
- Each pair sent the exact same batch to both strategies; treatment order was exactly balanced at
  100 bulk-first and 100 combined-first in every full cell.
- Each full cell used 200 measured pairs and 20 discarded warmup pairs.
- Primary block: five identifier mixes × three seeds at c=1 (15 cells).
- Identifier-type confirmation: four DOI-only mix cells at c=1.
- Moderate-load direction check: 100/0, 50/50, and 0/100 at c=4 and c=8, two seeds each (12 cells).
- Full cells: 31; measured pairs: 6,200; measured HTTP requests: 12,400.
- Including warmups, the full cells sent 13,640 HTTP requests. The 20-pair preflight is excluded from
  these totals.
- Primary metric: endpoint `_meta.processing_time_ms`. Client latency was retained but was not used for
  the implementation decision because it includes this workstation's network path.

Canonical full-cell command:

```shell
python -m benchmarks.publications \
  --base-url https://annotator.ci.transltr.io \
  --method POST --batch-size 100 \
  --compare-strategies bulk-search combined-search \
  --identifier-file <corpus-file> --concurrency <1|4|8> \
  --requests 200 --warmup 20 --seed <seed> \
  --slo-basis server --json
```

The fixed corpora contain 900 unique, fully resolving identifier strings each. Primary alternative-ID pools split
their alternatives evenly between DOI and PMCID. The all-PMID pool was derived from already verified
mixed pools, so it overlaps those documents; the execution order of mix cells was rotated between seeds
to reduce correlation with shared-CI drift.

## Replicated c=1 results

Values are medians across seeds 20260828, 20260829, and 20260830; brackets are the run-to-run range.
All deltas are `combined-search − bulk-search`, so positive is a combined-search regression.

| PMID / alternative | bulk p90 | combined p90 | p90 delta | paired median delta | combined faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 / 0 | 31 [31–62] ms | 30 [30–60] ms | −1 [−2 to −1] ms | **+1 [1–1] ms** | 27.0% [16.5–40.0%] |
| 75 / 25 | 28 [26–29] ms | 33 [33–34] ms | **+5 [5–7] ms** | **+6 [6–6] ms** | 5.5% [3.0–11.5%] |
| 50 / 50 | 23 [23–27] ms | 34 [33–41] ms | **+11 [10–14] ms** | **+11 [10–11] ms** | 0.5% [0.0–5.5%] |
| 25 / 75 | 29 [28–29] ms | 35 [34–36] ms | **+7 [5–7] ms** | **+6 [5–6] ms** | 3.5% [1.5–5.5%] |
| 0 / 100 | 32 [31–32] ms | 33 [32–33] ms | +1 [1–1] ms | **0 [0–0] ms** | 35.0% [35.0–39.0%] |

The 0/100 row is a deliberate no-change control: both selectors invoke the same bulk alternative-ID
implementation, so its 0 ms paired median establishes the noise floor for marginal percentile
differences. The 100/0 row is therefore not evidence for combined search: its paired result says the
typical request was 1 ms slower, and the moderate-load repetitions below do not reproduce a p90 win.

Order does not explain the mixed-workload result. Across all primary mixed cells:

- bulk-first paired server medians were +5 to +11 ms;
- combined-first paired server medians were +5 to +11 ms.

Positive means `combined-search` was slower.

## DOI-only confirmation

One 200-pair c=1 run per mix used DOI as the only alternative identifier type.

| PMID / DOI | bulk p90 | combined p90 | p90 delta | paired median | order medians (bulk-first / combined-first) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 75 / 25 | 26 ms | 37 ms | **+11 ms** | **+7 ms** | +7 / +8 ms |
| 50 / 50 | 25 ms | 36 ms | **+11 ms** | **+11 ms** | +11 / +11 ms |
| 25 / 75 | 33 ms | 37 ms | **+4 ms** | **+5 ms** | +6 / +5 ms |
| 0 / 100 | 33 ms | 33 ms | 0 ms | **0 ms** | 0 / 0 ms |

This confirms that PMCIDs in the primary pools were not responsible for the result.

## Moderate-load confirmation

These paired cells are directional checks, not standalone capacity measurements.

| concurrency | mix | bulk p90 range | combined p90 range | p90 delta range | paired median range |
| ---: | --- | ---: | ---: | ---: | ---: |
| 4 | 100 / 0 | 37–38 ms | 37–38 ms | 0 ms | 0 to +1 ms |
| 4 | 50 / 50 | 27–27 ms | 40–43 ms | **+13 to +16 ms** | **+12 ms** |
| 4 | 0 / 100 | 39–41 ms | 40–41 ms | 0 to +1 ms | −1 to 0 ms |
| 8 | 100 / 0 | 49–57 ms | 52–52 ms | −5 to +3 ms | +1 ms |
| 8 | 50 / 50 | 49–52 ms | 67–70 ms | **+15 to +21 ms** | **+13 to +14 ms** |
| 8 | 0 / 100 | 53–55 ms | 51–55 ms | −2 to 0 ms | −1 to 0 ms |

Every arm remained under the benchmark's 150 ms handler-time threshold with 100% HTTP success. The
50/50 direction strengthened under load; both endpoint controls remained near zero.

## Integrity

Across all 6,200 measured full-cell pairs:

- 6,200 valid pairs and 0 invalid pairs;
- 100% HTTP 200 and 100% identifier resolution in both arms;
- 0 request-ID mismatches;
- 0 lookup-strategy attribution mismatches;
- 0 fallback samples and 0 missing fallback attribution;
- 0 semantic response mismatches;
- 0 unresolved pairs or identifiers;
- exact 50/50 treatment order in every cell;
- exact changed-path order balance in every cell that exercised different code.

## Interpretation

The result is consistent with the query shapes. `bulk-search` starts a specialized PMID `_mget` and a
single alternative-ID terms search concurrently. `combined-search` saves a logical Elasticsearch call,
but the mixed query must resolve both `_id` and identifier clauses in one search operation. The benchmark
shows that this does not beat two specialized concurrent operations. This is an inference from the
measurements, not a direct Elasticsearch profile.

There is no measured routing threshold:

- any mixed request favors `bulk-search`;
- an all-alternative request already uses the bulk implementation;
- an all-PMID request is an effective tie and supplies no repeatable advantage worth another branch.

Adaptive routing would therefore add code and operational surface without a demonstrated latency gain.

## Caveats

- Fixed 900-document pools and warmups make this a heavily warm-cache comparison, not independent
  first-touch latency. Balanced paired order controls first-order cache bias but cannot make both arms
  cold.
- The first all-PMID primary cell had much higher absolute tails than the next two (bulk/combined p90
  62/60 ms versus 31/30 ms). Its paired median remained +1 ms, so the implementation comparison was
  stable even though the shared environment was not.
- The all-PMID pool reuses 675 raw IDs from the 75/25 pool and 225 from the 50/50 pool. Rotated cell
  order reduces temporal bias, but absolute cross-mix latency should not be compared as if every pool
  were disjoint.
- The retained 2022 Europe PMC corpus is fully resolving but is not a measured production traffic
  distribution. The retained corpus files do not independently prove that every alternative identifier
  maps to a different underlying document because the original generator manifest was not retained.
- Zero fallback samples prove that the requested normal paths stayed active; this curated corpus does
  not estimate fallback frequency or fallback cost on production traffic.
- CI is shared, single-replica infrastructure. The replicated c=1 paired results carry more weight than
  marginal c=8 p90 fluctuations.
- `processing_time_ms` is integer handler time. It excludes response serialization and transfer, and
  one-millisecond endpoint differences are below the useful resolution of this experiment.
- Corpus mixes are aggregate pool proportions; each 100-ID batch is a random sample and does not enforce
  its nominal ratio exactly. The coarse 0/25/50/75/100% grid cannot exclude a very narrow crossover,
  but no measured cell—including 100% PMID—shows a repeatable paired advantage that would motivate
  searching for one.
- Different calendar-quarter/document pools back the mixed-ratio cells, and their mean response sizes
  span 167.8–180.3 kB. Within-cell paired deltas remain like-for-like; the curve across ratios is not a
  controlled same-document dose response.
- Compact aggregate JSON was retained rather than raw pair observations, so confidence intervals and
  temporal-drift analysis cannot be reconstructed after the fact.

## Artifacts

- `SUMMARY.json` contains the mechanical aggregate used by this report.
- `primary-*.json`, `doi-confirm-*.json`, and `load-*.json` are the full harness reports.
- `deployment-*.json` and `status-*.json` retain the deployment gates.
- `run_primary.sh`, `run_doi_confirmation.sh`, and `run_load_c{4,8}.sh` retain the exact orchestration.
- `manifest.sha256` hashes the retained report, corpora, scripts, and JSON artifacts.
