# biothings annotator

Annotation service for the Translator Project. Originally apart of the 
[pending.api](https://github.com/biothings/pending.api/blob/b7a5a5cb2a890da8563a105e1da1215d7eb09e55/web/handlers/annotator.py),
we've broken it out into it's own service


### Installation


##### Environment Setup 
```shell
git clone https://github.com/biothings/biothings_annotator
python3 -m venv biothings_annotator
cd biothings_annotator
pip install .
```
##### one-line command installation
```shell
pip install -e git+https://github.com/biothings/biothings_annotator#egg=biothings_annotator
```

### Structure
```shell 
biothings_annotator
├── annotator <- annotation backend logic
└── application <- web service logic
    ├── cli
    ├── configuration
    ├── exceptions
    ├── middleware
    └── views
```

`biothings_annotator` is as a package is separated into the annotator logic and web handler logic. 
The annotator logic primarily exists within `annotator/annotator.py` and `annotator/transformer.py`.
Whereas the web server application is defined entirely within `application` directory. 


### Command-line Interface
The `__main__.py` defines the entrypoint to the module for running the `sanic` web server. After
installation run the following to command to start the annotator service:

```shell
python3 -m biothings_annotator
```

###### Command-line Implementation
The `__main__.py` file points to the application module where it will run the `main` function within
the launcher. The majority of our implementation exists within the
`biothings_annotator/application/cli` module. We store the main command line handling logic in
`cli/interface.py` with argument definitions and other argument handling in `cli/arguments.py`. We
wanted to maintain the same command line interface as sanic. `sanic` has a `cli`
module where it defines the `SanicCLI`class for handling their command-line implementation. However
we also have additional arguments we want to support. So we override the `SanicCLI` to acquire the
original parser handlers. The command-line steps are then divided in three steps shown below.

```python
# Entrypoint

cli = AnnotatorCLI()
cli.attach()
cli.parse()
cli.run()
```

The `attach` method aggregates all of the `ArgumentParser` instances stored in what `sanic` 
defines as `Group` objects. In order to add our custom arguments we define our own implementations
of the `Group` argument parsers to be called during the `attach` method. 

The `parse` method then builds the parsers from `Group` objects. While we want to support the same
interface as `sanic`, we do limit some of the options. The main limit is the `target` option which
points to a module or factory for building the `AppLoader` instance. We hard-set that and a couple
other options so that we cannot accidently change the path we point to for building the web server
implementation. Our factory method for generating the `sanic.Sanic` application instance is defined
with `cli/target.py`.

```python

# Original AppLoader instance
app_loader = AppLoader(
    self.args.target, self.args.factory, self.args.simple, self.args
)

# biothings-annotator AppLoader instance
application_loader = AppLoader(
    module_input=self.args.target, # hard-coded to ""
    as_factory=self.args.factory, # hard-coded to False
    as_simple=self.args.simple, # hard-coded to False
    args=self.args,
    factory=functools.partial(build_application, self.server_configuration),
)

# AppLoader definition
class AppLoader:
    """
    A helper to load application instances.
    Args:
        module_input (str): The module to load the application from.
        as_factory (bool): Whether the application is a factory.
        as_simple (bool): Whether the application is a simple server.
        args (Any): Arguments to pass to the application factory.
        factory (Callable[[], SanicApp]): A callable that returns a Sanic application instance.
    """

    def __init__(
        self,
        module_input: str = "",
        as_factory: bool = False,
        as_simple: bool = False,
        args: Any = None,
        factory: Optional[Callable[[], SanicApp]] = None,
    ) -> None:
```

The `run` method builds the `AppLoader` instance and the runtime arguments builder method. The
default command line arguments are shown below:

```python
default_parameters = {
    "access_log": None,
    "auto_tls": False,
    "coffee": False,
    "debug": False,
    "fast": False,
    "host": None,
    "motd": True,
    "noisy_exceptions": None,
    "port": None,
    "single_process": False,
    "ssl": None,
    "unix": "",
    "verbosity": 0,
    "workers": 1,
}
```

Some of these arguments are hard-set by the configuration file defaults and cannot be changed at the
command-line unless the configuration file is modified. 

##### Examples

```shell
python3 -m biothings_annotator --host "172.84.29.248"
python3 -m biothings_annotator --host "172.84.29.248" --port 9384 
python3 -m biothings_annotator --host "172.84.29.248" --port 9384 --workers 12 
python3 -m biothings_annotator --host "172.84.29.248" --port 9384 --workers 12 --debug
```

##### Runtime configuration

##### OpenTelemetry tracing

The service can export Sanic request spans and downstream HTTPX spans to a
Jaeger collector using OTLP over HTTP. Tracing is disabled by default and can
be enabled without changing the configuration file:

```shell
export OPENTELEMETRY_ENABLED=true
export OPENTELEMETRY_SERVICE_NAME=BioThingsAnnotator
export OPENTELEMETRY_JAEGER_HOST=http://localhost
export OPENTELEMETRY_JAEGER_PORT=4318
python -m biothings_annotator
```

The exporter sends spans to
`$OPENTELEMETRY_JAEGER_HOST:$OPENTELEMETRY_JAEGER_PORT/v1/traces`. Set
`OPENTELEMETRY_EXCLUDED_URLS` to a comma-separated list of regular expressions
to override the configured route exclusions. The Helm deployment enables
tracing and targets `http://jaeger-otel-collector.sri:4318` by default.

The annotator query backend is controlled with `ANNOTATOR_QUERY_BACKEND`. Supported values are
`biothings` and `elasticsearch`; when unset, the service uses `biothings`.
The Helm/Jenkins deployment defaults set `ANNOTATOR_QUERY_BACKEND=elasticsearch` and
`ELASTICSEARCH_CONNECTION=ci`; set `ANNOTATOR_QUERY_BACKEND` to `biothings` during deployment
to switch back.
Set `ELASTICSEARCH_CONNECTION` to one of the named presets in
`biothings_annotator/annotator/settings.py`. The `ci` preset points at
`http://elasticsearch.es-core-components.svc.cluster.local:9200`. The `ci_local_forward` preset is
for local port-forward use; `ci_forward` remains as a deprecated alias.
The `/version` endpoint reports the active `query_backend` and, when Elasticsearch is active,
the selected `elasticsearch_connection`.

##### Per-request query backend override

The `GET /curie/{curie}`, `POST /curie`, and `POST /trapi` endpoints accept an optional
`query_backend` query parameter. Omit it to use the backend selected for the deployment by
`ANNOTATOR_QUERY_BACKEND`. Use the canonical values `biothings` or `elasticsearch` to override the
backend for only that request; `es` is accepted as an alias for `elasticsearch`.
Unsupported values are ignored and the request uses the deployment default.
Successful query responses include the canonical backend in the `X-Query-Backend` response header.
When a recognized CURIE prefix is unavailable through that backend, its result contains a structured
`skipped` status with the source, selected backend, and `source_unavailable_for_backend` reason.
`X-Skipped-Curie-Prefixes` also summarizes the affected prefixes as comma-separated values. Unknown
CURIE prefixes are not included in this header.

```shell
curl 'http://localhost:9000/curie/NCBIGene:1017?query_backend=biothings'
curl -X POST 'http://localhost:9000/curie/?query_backend=elasticsearch' \
  -H 'Content-Type: application/json' \
  -d '{"ids":["NCBIGene:1017","CHEBI:100024"]}'
curl -X POST 'http://localhost:9000/trapi/?query_backend=es' \
  -H 'Content-Type: application/json' \
  -d '{"message":{"knowledge_graph":{"nodes":{},"edges":{}}}}'
```

##### PubMed metadata

`PMID` CURIEs are routed unchanged to the standalone `annotator-pubmed` Elasticsearch alias. When the
annotation-hub [`pubmed_metadata`](https://github.com/biothings/annotation-hub/tree/add-pubmed-metadata)
source is built and indexed there, the default annotation response includes its `pubmed` object
(journal, title, volume, issue, publication date, and abstract). Like the other first-class
biomedical sources, PubMed has its own annotator client configuration rather than being merged into
`annotator_extra`.

For the `biothings` query backend, the annotator discovers available sources from the API's
`/api/list` endpoint using a short-lived, per-host cache. Discovery requests revalidate intermediary
caches, concurrent refreshes share one request, and discovery failures use a brief retry backoff.
While `pubmed` is absent from that authoritative list, PMID requests return a one-item,
not-found-shaped skipped result without making a downstream PubMed annotation query and set
`X-Skipped-Curie-Prefixes: PMID`. Skipped responses use `Cache-Control: no-store`. The `notfound`
field preserves the normal result shape, while `skipped` indicates that the PubMed annotation lookup
was not made:

```json
{
  "PMID:31763219": [
    {
      "query": "PMID:31763219",
      "notfound": true,
      "skipped": true,
      "reason": "source_unavailable_for_backend",
      "source": "pubmed",
      "query_backend": "biothings"
    }
  ]
}
```

The future BioThings endpoint is already configured as `/pubmed`. Once `pubmed` appears in the
source list and its metadata is available, the annotator automatically constructs that client and
queries it without another code or configuration change. A source-discovery timeout, invalid
response, or server error returns HTTP 503 with `Cache-Control: no-store` rather than incorrectly
reporting a skip.

```shell
curl 'http://localhost:9000/curie/PMID:12345678?query_backend=elasticsearch'
```

##### Dedicated document metadata endpoint

The dedicated publications API is the PubMed-only fast path requested by the
[Core Components Working Group](https://github.com/NCATSTranslator/Core-Components-Working-Group/issues/15).
It supports the legacy batch query contract, a path-based single-publication lookup, and a JSON batch
contract:

```shell
# Legacy-compatible batch lookup
curl 'http://localhost:9000/publications?pubids=PMID:30690000,PMID:82374&request_id=request-123'

# Single-publication lookup
curl 'http://localhost:9000/publications/PMID:30690000?request_id=request-123'

# JSON batch lookup, mixing identifier types
curl -X POST 'http://localhost:9000/publications' \
  -H 'Content-Type: application/json' \
  -d '{"ids":["PMID:30690000","PMC:PMC1904490","doi:10.1242/jcs.03153"],"request_id":"request-123"}'
```

Both batch forms accept at most 100 identifiers; the path form looks up one identifier. An optional
`request_id` is round-tripped in the response metadata. For `POST`, it can be supplied in the JSON
object as shown above.

The response contains legacy-compatible `_meta`, `results`, and `not_found` sections, keyed by the
identifier as submitted. Missing source values are returned as empty strings. The publication date is
projected from PubMed's verbatim rendering when the index carries it, so month ranges survive as
CCWG#15 specifies (`"pub_month": "Sep-Dec"` for `PMID:8000234`); otherwise it falls back to splitting
the indexed ISO `pub_date` into year, month, and day.

The index carries the verbatim value in `pubdate_raw` — whatever the upstream exporter emits, the
in-house ingest transformation normalizes it to that field, which is also the field the capability probe
checks. `pub_date` is additionally read as a verbatim value purely defensively, so that a raw value
landing there is not flattened to empty strings if that transformation ever changes. It cannot misread
anything: the verbatim and ISO parsers accept disjoint shapes, so `"2019-03-15"` is only ever read as an
ISO date and `"1994 Sep-Dec"` only as a verbatim one.

A bare year range is the one shape that collides with an ISO date, since both open with `YYYY-`. It is
projected losslessly into `pub_year` — `"1987-1988"` gives `{"pub_year": "1987-1988", "pub_month": "",
"pub_day": ""}` — because the legacy fields have no home for a second year and `pub_month` would misfile
one. Reading it as ISO instead would return `"1987"` and drop the closing year. A two-digit tail such as
`"1987-88"` keeps its ISO reading, because it cannot be distinguished from the month in `"2026-07"`.

##### Accepted identifier types

`PMID`, `PMC`, and `doi` are accepted. Prefix casing is matched case-insensitively across the ASCII
spellings only, and a PMCID keeps PubMed's doubled form — `PMC:PMC1904490`, not `PMC:1904490`. The
served patterns spell each prefix out as explicit case pairs to mirror the OpenAPI `PublicationId`
pattern character-for-character; `re.IGNORECASE` would case-fold non-ASCII letters such as `doİ:` into
a match that the published contract rejects and the index cannot resolve. Two further shape constraints
follow from the transport rather than the service:

- A DOI suffix contains slashes, so the path form relies on a `path` route converter to avoid
  truncating at the first segment.
- A DOI suffix may itself contain a comma, which the legacy comma-separated `pubids` form cannot
  express. Use the JSON body for those identifiers.

These routes are deliberately separate from the generic annotation pipeline. They always read the
`annotator-pubmed` Elasticsearch alias and retrieve only the `pubmed` source object. They do not
perform BioThings source discovery, CURIE grouping, extra annotation lookup, or per-request backend
selection. The request has a two-second total backend deadline by default (configurable with
`DOCUMENT_METADATA_REQUEST_TIMEOUT`) so a degraded Elasticsearch service fails quickly.

PMIDs are the document `_id`, so they resolve through one exact-ID Elasticsearch `_mget` for the whole
batch, including a complete batch of 100. PMCID and DOI resolve against `pubmed.identifiers` instead,
which costs one `_msearch` entry per identifier, so a PMID-only request stays on the single-request fast
path and only mixed requests pay for the scoped lookup. The behavioral performance test verifies that a
100-PMID request remains one backend request, and the load benchmark measures what that costs against
the 150 ms p90 service objective — see [Load benchmark](#load-benchmark-and-the-150-ms-objective).

The current PubMed index contains only `PMID:<digits>` document IDs and no `pubmed.identifiers` field,
so PMCID and DOI lookups return `not_found` until the index is rebuilt. That is the response CCWG#15
specifies for an identifier the service does not have, but it is indistinguishable from a genuinely
absent paper, so the index shape is checked separately — see
[Verifying the PubMed index shape](#verifying-the-pubmed-index-shape).

The reindex is treated as a deployment prerequisite rather than something the service polices. The
identifier routing, the scoped lookup, and the capability probe all ship here so that PMCID and DOI
support becomes live the moment the index is rebuilt, with no further code change. Deliberately, the
endpoint does not refuse PMCID and DOI requests while the field is absent: a startup gate would also
take down the PMID fast path, which works against the index as it stands today. Use
`check_index_fields()` to tell "not in this index" from "not a real paper" before rollout.

##### Verifying the PubMed index shape

`DocumentMetadataService.check_index_fields()` probes the live mapping through the alias and reports
which of the fields the API depends on actually exist:

```json
{
  "index": "annotator-pubmed",
  "fields": {"pubmed.identifiers": false, "pubmed.pubdate_raw": false},
  "missing_required_fields": ["pubmed.identifiers"],
  "multi_identifier_lookup": false,
  "verbatim_publication_date": false
}
```

It reports rather than raises. `pubmed.identifiers` is required for DOI and PMCID lookup to work at
all, so its absence sets `multi_identifier_lookup` to `false`; `pubmed.pubdate_raw` only changes the
precision of the projected date and has a working fallback, so it is informational.

`fields` reports mapping presence, while the required-field gate additionally demands that the field be
searchable. A field mapped with `index: false` is listed in the field-caps response but matches nothing
when queried, so it appears as `"pubmed.identifiers": true` **and** in `missing_required_fields` — that
combination is the signature of a field that exists but was mapped unsearchable. A fatal startup
assertion would be wrong here, because refusing to boot over a missing field would also take down the
PMID fast path that does work.

The probe reads the mapping rather than sampling documents, which is what separates "this field is not
in the index" from "this paper is not in the index" — a DOI query against an unmapped field returns
zero hits and no error. It stays useful after rollout: it catches a later reindex that drops the field,
and an alias left pointing at a stale index.

With the CI Elasticsearch service forwarded to `localhost:9200`, run the opt-in live checks with:

```shell
RUN_PUBMED_ES_INTEGRATION=1 \
PUBMED_INTEGRATION_ELASTICSEARCH_CONNECTION=ci_local_forward \
python -m pytest -q tests/test_pubmed.py tests/test_document_metadata.py -m integration
```

The document metadata live checks assert the index shape, resolution by every identifier type,
case-insensitive matching, and an upper bound of three identifiers per record. That bound is a bad-export
guard: pubmed2db PR #7 limits a record to its own identifiers, so a record carrying hundreds means the
export regressed and is pulling in cited references' DOIs.


###### Identifier lookup: two measured optimizations

Both were measured against the CI Elasticsearch cluster (`es-core-components-cluster`, index
`pubmed_20260824_ybg350zl_202608250007`, 41.0M documents, 21.5 GB per copy, 5 primary shards and 2
replicas), using identifiers sampled from the live index rather than synthesized ones.

**Deduplicating `pubmed.identifiers` so the PMID is not stored twice — adopted, storage win only.**
The PMID is already the document `_id`, so carrying it in `identifiers` as well was redundant. The
field now holds 43.5M values across 41.0M documents (1.06 per document; 80% of documents carry any
identifier at all), and re-adding the PMID would take that to 84.5M, near enough a doubling.

Measured by building two indices from the same 29,983 real documents with the live mapping and
analysis settings, differing only in whether the PMID is present in `identifiers`, then force-merging
both to one segment:

| | deduped | PMID re-added | delta |
| --- | --- | --- | --- |
| index store size | 31.0 MB | 31.7 MB | **+2.3%** |
| `pubmed.identifiers` total | 0.9 MB | 1.4 MB | +50.1% |
| — inverted index | 0.5 MB | 0.7 MB | +48.4% |
| — doc_values | 0.5 MB | 0.7 MB | +51.8% |
| `_source` | 26.5 MB | 26.7 MB | +1.0% |
| `_msearch` took, 100 identifiers | 4 ms | 4 ms | **0%** |
| `_mget` response, 100 PMIDs | 152.7 kB | 154.2 kB | +1.0% |

Extrapolated to the live index that is **1.0 GB saved per copy, 3.0 GB across the three copies** — the
field itself roughly halved, which is 2.3% of the index. The latency gain is nil, and measurably so:
identical `_msearch` timings and a `_mget` response 1% smaller. Worth having as a storage and index-size
change; it is not a latency optimization and should not be quoted as one.

**Resolving to `_id` first, then one combined `_mget` — keep off pending an endpoint A/B.** The idea is
to ask the `_msearch` only for `_id`, then fetch everything through a single exact-ID `_mget`. It is
an explicit `DocumentMetadataService` option. The endpoint keeps `current` as its hard-coded safe default
and exposes the temporary per-request benchmark selector below:

| identifier mix | current total | two-phase total | delta | current `_msearch` took | two-phase `_msearch` took | ES round trips |
| --- | --- | --- | --- | --- | --- | --- |
| 75 PMID / 25 other | 154.0 kB | 158.9 kB | **+3.2%** | 9 ms | 8 ms | 1 parallel → 2 serial |
| 50 / 50 | 160.5 kB | 167.1 kB | **+4.1%** | 12 ms | 12 ms | 1 parallel → 2 serial |
| 25 / 75 | 166.0 kB | 173.7 kB | **+4.7%** | 18 ms | 16 ms | 1 parallel → 2 serial |
| 0 / 100 other | 168.7 kB | 181.9 kB | **+7.8%** | 22 ms | 21 ms | 1 → 2 serial |

These measurements do not establish full-path latency. The timing columns are only the top-level
`_msearch.took`; the two-phase value omits the `_mget` that follows it. They do show that source
retrieval is not an expensive part of `_msearch`: 100 identifiers that all resolve take 22 ms of
Elasticsearch wall-clock, and `"_source": false` removes about 1 ms. It cuts that leg's response by 84%
(169 kB to 26 kB), but those bytes reappear in the combined `_mget` with its per-document envelope, so
total backend response bytes rise 3–8%. The extra serial round trip makes a slowdown plausible, not
measured; use the single-deployment endpoint A/B below before calling it a latency regression.

Two corrections to earlier reasoning come out of this. The shard fan-out is not the practical problem it
looked like: per-identifier cost *falls* with batch size, 0.40 ms at 10 identifiers to 0.22 ms at 100,
so Elasticsearch is parallelising the sub-searches well across the 5 shards. And the identifier path is
not where the latency budget goes at all — 22 ms for a fully-resolving 100-identifier batch, against the
~114 kB of response body that the [load benchmark](#load-benchmark-and-the-150-ms-objective) shows to be
the actual constraint. Optimisation effort belongs on payload size, not on identifier resolution.

A measurement note for anyone repeating this. Run through an SSH tunnel, every Elasticsearch round trip
costs 90-190 ms and drifts during a session, which is two orders of magnitude above in-cluster and more
than the entire effect being measured. Tunnel wall-clock does establish how the forwarded path behaves,
but it exaggerates the production cost of a second round trip. Per-sub-request `took` values must not be
summed either — Elasticsearch runs `_msearch` entries concurrently, so their sum is total work, not
latency. Compare the complete endpoint paths through CI's own `processing_time_ms` instead.

##### Load benchmark and the 150 ms objective

CCWG#15 sets a service objective of a 150 ms p90 for requests carrying up to 100 publication
identifiers. `benchmarks/publications` measures a deployment against it. The endpoint is meant as a
drop-in replacement for DocumentMetadataAPI, so the benchmark deliberately covers only
`/publications` — none of the generic annotation routes share its code path.

```shell
# The headline CCWG#15 case: 100 identifiers per request, against CI.
python -m benchmarks.publications --requests 200

# Load-bearing sweep: where does the objective stop holding?
python -m benchmarks.publications --ramp 1,4,8,16 --requests 200

# The JSON body form, and the cached case the specification recommends.
python -m benchmarks.publications --method POST
python -m benchmarks.publications --unique-ratio 0.0 --hot-pool 200

# Mixed identifiers, which take the per-identifier _msearch path instead of the batched _mget.
python -m benchmarks.publications --pmid-ratio 0.5

# Temporary one-deployment A/B selector. Every identifier batch goes to both implementations.
python -m benchmarks.publications --method POST --compare-lookup-strategies \
  --identifier-file real-publication-ids.txt --concurrency 1 \
  --requests 200 --warmup 20 --seed 2026

# A single arm remains available for an absolute load-bearing sweep.
python -m benchmarks.publications --lookup-strategy two-phase --ramp 1,4,8,16 --requests 200

# Machine-readable output; exit status is 0 only if every stage met the objective.
python -m benchmarks.publications --json --slo-basis server
```

`--lookup-strategy` sends the undocumented `X-Publications-Lookup-Strategy` benchmark header. The
endpoint defaults to `current`, holds independent current and two-phase service instances, and echoes
the selection as `_meta.lookup_strategy`. The harness rejects a missing or mismatched attribution rather
than admitting that latency into the result. `--compare-lookup-strategies` performs the A/B in one
invocation: it precomputes each batch, sends that exact batch to both implementations, and balances
current-first/two-phase-first order after the batches are known. In comparison mode, `--requests` and
`--warmup` count pairs, so 200 measured pairs produce 400 HTTP requests. The measured pair count must be
even and at least two, ensuring both request orders are represented. `--concurrency` remains the maximum
number of HTTP requests in flight; the two members of a pair are sequential rather than doubling the
offered load.

The paired report keeps current-first and two-phase-first deltas separate as well as combined. That is
necessary because the second request can benefit from Elasticsearch state warmed by the first. Balanced
ordering is applied separately to pairs containing DOI/PMCID identifiers and to PMID-only controls, so
the changed path is represented in both orders. This controls first-order bias, but one shared deployment
cannot give both treatments a cold first lookup. If the order strata disagree in direction, treat the run
as cache/order-sensitive rather than declaring a winner. The mixed A/B wall time is not a standalone
capacity measurement; use the existing single-strategy mode with `--ramp` for that. Comparison mode is
intentionally closed-loop and cannot be combined with `--users`. The selector is temporary measurement
scaffolding and should be removed with the losing implementation after the A/B.

Comparison mode requires `--identifier-file` with one real, resolving identifier per line, at least one
batch's worth of identifiers, and at least one DOI or PMCID; blank lines and lines beginning with `#` are
ignored. Prefer one identifier per distinct document and enough DOI/PMCID entries for the reported mix to
represent the traffic being decided. Synthesized DOI values mostly miss, while an all-PMID corpus sends
both implementations down the same `_mget` path, so neither can decide whether the two-phase source fetch
is faster. Any identifier reported as `not_found` by either arm invalidates its pair and makes the
comparison exit nonzero.

###### Reading the numbers

Every run reports two latencies per request, because they answer different questions and can
disagree:

- **server** is the endpoint's own `_meta.processing_time_ms`. It is what the service controls and is
  comparable from any vantage point, so it is what `--slo-basis` gates on by default.
- **client** is wall-clock time to a fully-read response, which is what a UI actually experiences. It
  includes the network path from wherever the benchmark runs. A full batch of 100 returns roughly
  115 kB of abstracts, so from outside the cluster transit and transfer alone add 150–250 ms at p90 and
  the client-side verdict fails on network cost rather than on service time. Run the benchmark from
  inside the cluster, or from the UI's own vantage point, before reading a client-side number as an SLO
  result. The report prints the measured `net p90` difference so this is never invisible.

Four methodology choices are worth knowing about, because each one would otherwise flatter the result:

- **Warmup is discarded.** Each stage first issues throwaway requests to fill the keep-alive pool, so
  no measured sample is charged for a TLS handshake. The warmup uses a separate seeded draw; synthetic
  fresh identifiers therefore stay separate, while a fixed identifier pool can overlap and is reported
  as a cache-warming workload.
- **Identifiers are drawn fresh by default.** `--unique-ratio 1.0` makes every lookup a first-time
  lookup, which is the cold-cache bound. Elasticsearch caches aggressively — the same batch replayed
  drops from roughly 70 ms to under 30 ms — so a benchmark that reused identifiers would report the
  best case as if it were typical. `--verify-corpus` is available for a known-present corpus, and any
  run using it is labelled `cache_primed`, because verification is itself a query that warms the cache.
- **The hit ratio is reported.** PMIDs are drawn at random from the range PubMed has issued, so around
  96% resolve. That matters because an all-`not_found` response is cheap to serve; a run whose
  identifiers mostly missed would show a fast p90 for work the service never did.
- **Percentiles are nearest-rank.** An interpolated p90 reports a latency that was never observed. The
  report also prints the fraction of requests strictly under the threshold, which is the more literal
  reading of "90% of requests should take <150ms" and needs no interpolation convention to reproduce.

###### Measured against CI

Full batches of 100 identifiers against `https://annotator.ci.transltr.io`, cold cache, server-side
latency in milliseconds:

| workload | p50 | p90 | p95 | p99 | verdict |
| --- | --- | --- | --- | --- | --- |
| 1 identifier | 5 | 7 | 7 | 8 | pass |
| 10 identifiers | 12 | 16 | 18 | 21 | pass |
| 100 identifiers, `GET` | 62 | 73 | 80 | 84 | pass |
| 100 identifiers, `POST` | 68 | 77 | 82 | 86 | pass |
| 100 identifiers, replayed (warm cache) | 27 | 49 | 55 | 62 | pass |
| 100 identifiers, 50% PMCID and DOI | 34 | 54 | 181 | 199 | pass at p90 |

The PMID fast path meets the objective with roughly half the budget to spare, and scales sublinearly
with batch size: a hundredfold larger batch costs about ten times a single lookup, which is the
batched `_mget` behaving as intended.

Sweeping concurrency, across three independent runs plus a single-identifier control:

| concurrency | run A | run B | run C | 1 id (control) |
| --- | --- | --- | --- | --- |
| 8 | 46 rps / 52 ms | 37 rps / 45 ms | 35 rps / 44 ms | 85 rps / 6 ms |
| 16 | 81 rps / 83 ms | 85 rps / 74 ms | 63 rps / 78 ms | 156 rps / 6 ms |
| 24 | 109 rps / 106 ms | 100 rps / 109 ms | 86 rps / 77 ms | 184 rps / 6 ms |
| 32 | — | 106 rps / 152 ms | 99 rps / 129 ms | 221 rps / 6 ms |

Under smooth closed-loop load the objective holds to about 100 rps at 24 concurrent full batches, and
the p90 reaches the 150 ms line around 32. The single-identifier control never leaves 6 ms, so nothing
about the concurrency itself is hard: what costs is the response body, and a full batch is ~114 kB of
which **abstracts are 75%** (titles 8%). Caddy compresses it 2.9x to ~42 kB on the wire.

A fourth run measured a knee at 12 concurrent, with the p90 reaching 720 ms at 16 — roughly an order of
magnitude worse than the three runs above at the same concurrency, and with throughput plateauing rather
than climbing. It did not reproduce. CI is a shared single-replica deployment and the benchmark ran from
outside the cluster, so a run like that should be treated as an environment sample rather than a
property of the service, and repeated before anything is concluded from it. **Run the ramp at least
twice before quoting a ceiling.**

###### Concurrency is not users

The concurrency figures above are a capacity instrument, not a headcount. A closed-loop worker issues
its next request the instant the previous one returns, so `c=8` describes eight requests permanently in
flight — eight infinitely impatient robots, not eight people. A reader who spends half a minute looking
at a result page before triggering another lookup occupies the service for about 90 ms of those 30
seconds, and therefore offers roughly 0.03 requests per second rather than the ~11 a saturated worker
offers. The two differ by nearly three orders of magnitude, which is why one cannot be read as the
other.

Little's Law converts between them:

```
users = throughput x (service latency + think time)
```

So the 46 rps that CI sustains inside the objective corresponds to:

| mean think time | requests per user | supported readers |
| --- | --- | --- |
| 5 s | 0.197 rps | ~230 |
| 10 s | 0.099 rps | ~460 |
| 30 s | 0.033 rps | ~1,380 |
| 60 s | 0.017 rps | ~2,750 |

The think time is an assumption about reader behaviour, not something the benchmark can measure, so the
range is the answer rather than any single row. Even the pessimistic end is far above expected Translator
UI traffic.

To measure a population directly instead of inferring one, use user mode:

```shell
# 300 readers, each pausing ~30 s between lookups, for 90 seconds.
python -m benchmarks.publications --users 300 --think-time 30 --duration 90
```

User mode differs from the concurrency ramp in three ways that all matter:

- **Think times are exponentially distributed**, not fixed. A fixed gap keeps simulated users locked in
  whatever phase they started in, producing periodic bursts a real independent population does not have.
  Arrivals are also staggered across the first think-time window, so the run does not begin with a
  synchronized thundering herd.
- **Users share one popularity-ranked catalogue** (`--catalog-size`, `--zipf`). Real readers' interests
  overlap heavily, and that overlap is what a backend cache actually gets to absorb. Independent random
  draws per user would hide it. Classic Zipf is the default; `--zipf 0` gives a uniform catalogue for
  comparison.
- **The report distinguishes offered from achieved rate.** A population that was served without
  saturating the service bounds nothing from above, and the report says so rather than letting the
  achieved rate be mistaken for a ceiling.

Measured against CI at a 30 s think time, over 300 s so the joining transient has washed out:

| readers | offered | achieved | p50 | p90 | p99 | success | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 300 | 10 rps | 12 rps | 31 | 42 | 54 | 100% | pass |
| 600 | 20 rps | 25 rps | 25 | 33 | 56 | 100% | pass |
| 1,200 | 40 rps | 42 rps | 22 | **28** | 38 | 100% | pass |
| 2,400 | 80 rps | 53 rps | 31 | **808** | 1554 | 100% | fail |

So roughly **1,200 concurrent readers** fit inside the objective, with the p90 at 28 ms — a fifth of the
budget. At 2,400 the population offers 80 rps, the service delivers 53, and the p90 goes to 808 ms.

Worth noting that 1,200 readers pass at a *better* p90 (28 ms) than 100 readers do (87 ms, p99 333 ms).
That is not noise: at a low request rate the shared hot set falls out of cache between requests, so a
lightly loaded service does more cold lookups than a moderately loaded one.

The population fails at 53 rps while the closed-loop ramp sustained ~100 rps, and the difference is
**burstiness**, not a contradiction. Closed-loop load is perfectly smooth — exactly N requests in flight,
never more. Exponential think times produce Poisson arrivals, whose instantaneous rate clumps well above
its mean, and those clumps queue behind the 8 Sanic workers. Real traffic is bursty, so the lower number
is the more realistic one and the smooth ramp should be read as an optimistic bound.

Around that rate the service is at its edge. One 100 rps run was served cleanly; another at the same
offered rate shed about 1.5% of requests as HTTP 500s, which is the two-second backend deadline
(`DOCUMENT_METADATA_REQUEST_TIMEOUT`) doing what it was built to do. That matters for how capacity is
read: **failures leave the latency distribution, so a stage that sheds load posts a *better* p90 than one
that serves everything slowly.** The benchmark gates its capacity figure on a 99% success rate for that
reason, and flags any stage that passes on latency while shedding.

One limit on all of the above. At these rates a single load generator becomes a plausible bottleneck of
its own — 90 rps of 92 kB responses is around 8 MB/s to decompress and parse on one host. Server-side
latency is measured in the handler and stays trustworthy, so the report uses it as the discriminator: a
shortfall in achieved rate alongside a healthy server-side p90 and no errors points at the generator,
and the report says so instead of crediting the service with a ceiling it was never pushed to. Settling
it needs a run from inside the cluster, or a generator split across hosts.

###### Running it as a test

The benchmark is also wrapped as an opt-in pytest module. The offline tests cover the harness itself —
percentile arithmetic, verdict boundaries, and the accounting that keeps a failed or malformed response
from scoring as a fast one — and run with the normal suite. The live tests generate real load and are
gated:

```shell
RUN_PUBLICATIONS_LOAD_TEST=1 python -m pytest -q tests/test_publications_load.py -m performance
```

`PUBLICATIONS_LOAD_TEST_BASE_URL`, `PUBLICATIONS_LOAD_TEST_REQUESTS`,
`PUBLICATIONS_LOAD_TEST_CONCURRENCY`, and `PUBLICATIONS_LOAD_TEST_SLO_BASIS` override the target and
the load. The ramp test reports the concurrency levels that held the objective rather than asserting a
specific one, because that number describes the deployment's current sizing rather than the service.


### Builds

```shell
docker
├── configuration
│   ├── Caddyfile
│   └── supervisord.conf
└── Dockerfile
```

We have a Dockerfile and service through docker-compose for the biothings-annotator service. The
Docker file lives in `~/docker/Dockerfile` and defines two build stages. The first pulls down the
repository and creates a wheel for the python package. There are two optional arguments for
controlling the cloning process. 

- `ANNOTATOR_REPO`
- `ANNOTATOR_BRANCH` 

The second build stage sets up the docker environment. It installs packages and then creates the
`annotator` user and home environment. It then creates a virtual environment for the `annotator` user
and installs the wheels generated from the previous builder stage

The entrypoint is set as:

```docker
ENTRYPOINT ["supervisord"]
CMD ["-c", "/etc/supervisor/supervisord.conf"]
```

This leverages supervisord to launch to different services. The first is the annotator web server

```shell
[program:python_app]
command=/home/annotator/venv/bin/python -m biothings_annotator --conf=/home/annotator/configuration/default.json
```

This command will call the `__main__.py` entrypoint of the package itself. This should start the sanic web
service for hosting the annotation service. For configuration of the service itself, modify the
configuration found under `biothings_annotator/application/configuration/sanic.json`.

The second service launched is caddy. We use caddy in this case as a reverse proxy.

```shell
[program:caddy]
command=caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
```

The default port for the web server is `9001`, and the caddy proxy forwards to that upstream web server via port
`9000` for deployment purposes. The main purposes at the moment for caddy are for compression and
potential future usage as a load balancer


###### docker build

- default 
    - `~/biothings_annotator$ docker build ./docker`
    - `~/biothings_annotator$ docker build . -f docker/Dockerfile`

- build arguments
    - `~/biothings_annotator$ docker build --build-arg ANNOTATOR_BRANCH=main ./docker/`
    - `~/biothings_annotator$ docker build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git ./docker/`
    - `~/biothings_annotator$ docker build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git --build-arg ANNOTATOR_BRANCH=main ./docker/`

- tag
    - `~/biothings_annotator$ docker build ./docker/ --tag=annotator`

- without caching
    - `~/biothings_annotator$ docker build ./docker/ --no-cache`


###### docker compose build
- default 
    - `~/biothings_annotator$ docker compose build`

- build arguments
    - `~/biothings_annotator$ docker compose build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git --build-arg ANNOTATOR_BRANCH=main ./docker/`


###### docker run
    - `~/biothings_annotator$ docker run <annotator-image-name>`


###### docker compose up 
    - `~/biothings_annotator$ docker run <annotator-image-name>`



### Tests
The tests are implemented with `pytest` in mind.
To install the test dependencies `pip install .[tests]`. 

- Test Overview `pytest --setup-plan`

```
(biothings_annotator) ~/biothings_annotator$ python3 -m pytest tests/ --setup-plan
==================================================================================== test session starts ====================================================================================
platform linux -- Python 3.10.12, pytest-8.2.2, pluggy-1.5.0 -- ~/biothings_annotator/bin/python3
cachedir: .pytest_cache
rootdir: ~/biothings_annotator
configfile: pyproject.toml
collected 51 items

tests/test_curie.py::test_curie_parsing[NCBIGene]
        SETUP    F curie_prefix['NCBIGene']
        tests/test_curie.py::test_curie_parsing[NCBIGene] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['NCBIGene']
tests/test_curie.py::test_curie_parsing[ENSEMBL]
        SETUP    F curie_prefix['ENSEMBL']
        tests/test_curie.py::test_curie_parsing[ENSEMBL] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['ENSEMBL']
tests/test_curie.py::test_curie_parsing[UniProtKB]
        SETUP    F curie_prefix['UniProtKB']
        tests/test_curie.py::test_curie_parsing[UniProtKB] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UniProtKB']
tests/test_curie.py::test_curie_parsing[INCHIKEY]
        SETUP    F curie_prefix['INCHIKEY']
        tests/test_curie.py::test_curie_parsing[INCHIKEY] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['INCHIKEY']

...
```
