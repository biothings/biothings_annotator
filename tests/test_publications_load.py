"""Tests for the /publications load benchmark and its SLO objective.

Two groups live here. The offline group verifies the harness itself: a benchmark
whose percentile arithmetic or verdict logic is wrong reports confidence it has
not earned, so that logic is tested like any other code. The live group is
opt-in, because it generates real load against a deployment.

    RUN_PUBLICATIONS_LOAD_TEST=1 python -m pytest -q tests/test_publications_load.py -m performance
"""

import os

import pytest

from benchmarks.publications import (
    SLO_THRESHOLD_MS,
    CorpusConfig,
    IdentifierCorpus,
    LatencySummary,
    RunPlan,
    Sample,
    SloVerdict,
    StageReport,
    Workload,
    percentile,
    render_text,
    run_plan,
    slo_met,
)
from benchmarks.publications.report import MIN_CEILING_SUCCESS_RATE, sustained_ceiling
from benchmarks.publications.runner import RunResult
from benchmarks.publications.users import UserModel, capacity_table, run_user_plan, supported_users

LIVE_BASE_URL = os.environ.get("PUBLICATIONS_LOAD_TEST_BASE_URL", "https://annotator.ci.transltr.io")
LIVE_REQUESTS = int(os.environ.get("PUBLICATIONS_LOAD_TEST_REQUESTS", "60"))
LIVE_CONCURRENCY = int(os.environ.get("PUBLICATIONS_LOAD_TEST_CONCURRENCY", "4"))
LIVE_BASIS = os.environ.get("PUBLICATIONS_LOAD_TEST_SLO_BASIS", "server")

requires_live_deployment = pytest.mark.skipif(
    os.environ.get("RUN_PUBLICATIONS_LOAD_TEST") != "1",
    reason="Set RUN_PUBLICATIONS_LOAD_TEST=1 to generate load against a live deployment.",
)


def _sample(client_ms: float, server_ms: int = 10, status: int = 200) -> Sample:
    return Sample(
        client_ms=client_ms,
        status=status,
        server_ms=server_ms,
        requested=100,
        found=100,
        response_bytes=1024,
    )


# --- HARNESS: PERCENTILES ---
@pytest.mark.unit
@pytest.mark.parametrize(
    "quantile, expected",
    [(0.50, 50), (0.90, 90), (0.95, 95), (0.99, 99), (1.0, 100)],
)
def test_percentile_is_nearest_rank(quantile: float, expected: float):
    """Nearest-rank always returns an observed sample, never an interpolated one."""
    assert percentile(list(range(1, 101)), quantile) == expected


@pytest.mark.unit
def test_percentile_of_single_sample_is_that_sample():
    assert percentile([7.5], 0.90) == 7.5


@pytest.mark.unit
@pytest.mark.parametrize("quantile", [0.0, -0.1, 1.1])
def test_percentile_rejects_quantiles_outside_the_unit_interval(quantile: float):
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], quantile)


@pytest.mark.unit
def test_percentile_of_empty_series_is_an_error_not_zero():
    """Returning 0.0 here would render an empty run as a passing one."""
    with pytest.raises(ValueError):
        percentile([], 0.90)


# --- HARNESS: SLO VERDICT ---
@pytest.mark.unit
def test_verdict_passes_at_exactly_ninety_percent_under_threshold():
    verdict = SloVerdict.evaluate([100.0] * 90 + [900.0] * 10, basis="server")
    assert verdict.met
    assert verdict.fraction_under_threshold == pytest.approx(0.90)
    assert verdict.headroom_ms == pytest.approx(SLO_THRESHOLD_MS - 100.0)


@pytest.mark.unit
def test_verdict_fails_just_below_ninety_percent_under_threshold():
    verdict = SloVerdict.evaluate([100.0] * 89 + [900.0] * 11, basis="server")
    assert not verdict.met
    assert verdict.fraction_under_threshold == pytest.approx(0.89)


@pytest.mark.unit
def test_verdict_treats_the_threshold_as_strictly_exclusive():
    """CCWG#15 asks for requests under 150 ms, so 150 ms itself does not count."""
    assert not SloVerdict.evaluate([SLO_THRESHOLD_MS] * 10, basis="server").met
    assert SloVerdict.evaluate([SLO_THRESHOLD_MS - 0.1] * 10, basis="server").met


@pytest.mark.unit
def test_verdict_and_summary_of_no_samples_are_absent_rather_than_passing():
    assert SloVerdict.evaluate([], basis="server") is None
    assert LatencySummary.from_values([]) is None


@pytest.mark.unit
def test_slo_met_is_false_when_a_run_produced_no_successful_samples():
    """An outage must not read as a pass just because no latency exceeded budget."""
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=1.0)
    stage.samples.append(Sample(client_ms=5000.0, error="ConnectTimeout", requested=100))
    result = RunResult(plan=RunPlan(base_url="https://example.invalid", workload=Workload()), stages=[stage])
    assert not slo_met(result, "server")
    assert not slo_met(result, "client")


@pytest.mark.unit
def test_slo_met_requires_every_ramp_stage_to_pass():
    fast = StageReport(label="c=1", concurrency=1, wall_seconds=1.0, samples=[_sample(10.0, 10)] * 10)
    slow = StageReport(label="c=8", concurrency=8, wall_seconds=1.0, samples=[_sample(10.0, 400)] * 10)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload(), ramp=(1, 8))
    assert slo_met(RunResult(plan=plan, stages=[fast]), "server")
    assert not slo_met(RunResult(plan=plan, stages=[fast, slow]), "server")


# --- HARNESS: STAGE ACCOUNTING ---
@pytest.mark.unit
def test_failed_samples_are_counted_but_excluded_from_latency():
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=2.0)
    stage.samples.extend([_sample(100.0, 20), _sample(100.0, 20)])
    stage.samples.append(Sample(client_ms=30_000.0, status=500, requested=100))
    stage.samples.append(Sample(client_ms=30_000.0, error="ReadTimeout", requested=100))

    assert stage.status_counts == {"200": 2, "500": 1, "ReadTimeout": 1}
    assert stage.client_latency().count == 2
    assert stage.client_latency().maximum == 100.0
    assert stage.throughput_rps == pytest.approx(2.0)


@pytest.mark.unit
def test_a_malformed_two_hundred_is_not_scored_as_a_success():
    """A 200 with an unreadable body is a failure, not a fast request."""
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=1.0)
    stage.samples.append(Sample(client_ms=5.0, status=200, error="malformed-response:KeyError", requested=100))
    assert stage.successful == []
    assert stage.client_latency() is None


@pytest.mark.unit
def test_network_overhead_is_the_client_minus_server_difference():
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=1.0)
    stage.samples.append(_sample(250.0, 100))
    assert stage.overhead_latency().p90 == pytest.approx(150.0)


@pytest.mark.unit
def test_identifier_stats_expose_the_hit_ratio_of_the_measured_batches():
    """An all-miss run is cheap to serve, so the hit ratio has to be visible."""
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=1.0)
    stage.samples.append(
        Sample(client_ms=10.0, status=200, server_ms=5, requested=100, found=40, not_found=60, response_bytes=2048)
    )
    stats = stage.identifier_stats
    assert stats["found_ratio"] == pytest.approx(0.40)
    assert stats["mean_batch_size"] == pytest.approx(100.0)


# --- HARNESS: WORKLOAD AND CORPUS ---
@pytest.mark.unit
def test_workload_rejects_a_batch_larger_than_the_documented_maximum():
    with pytest.raises(ValueError):
        Workload(batch_size=101)


@pytest.mark.unit
def test_get_requests_use_the_legacy_comma_separated_pubids_form():
    path, kwargs = Workload(batch_size=2).build_request(["PMID:1", "PMID:2"], "rid")
    assert path.startswith("/publications?")
    assert "pubids=PMID%3A1%2CPMID%3A2" in path
    assert "request_id=rid" in path
    assert kwargs == {}


@pytest.mark.unit
def test_post_requests_carry_identifiers_in_the_json_body():
    """A DOI suffix may contain a comma, which the pubids form cannot express."""
    identifiers = ["doi:10.1000/a,b"]
    path, kwargs = Workload(batch_size=1, method="POST").build_request(identifiers, "rid")
    assert path == "/publications"
    assert kwargs == {"json": {"ids": identifiers, "request_id": "rid"}}


@pytest.mark.unit
def test_a_seeded_corpus_draws_the_same_identifiers_every_run():
    first = IdentifierCorpus(CorpusConfig(seed=99)).batch(50)
    second = IdentifierCorpus(CorpusConfig(seed=99)).batch(50)
    assert first == second


@pytest.mark.unit
def test_batches_are_deduplicated_because_the_endpoint_deduplicates_too():
    corpus = IdentifierCorpus(CorpusConfig(seed=5))
    corpus.seed_hot_pool(1)
    assert corpus.batch(10, unique_ratio=0.0) == corpus.hot_pool


@pytest.mark.unit
def test_replaying_identifiers_requires_a_seeded_hot_pool():
    with pytest.raises(ValueError):
        IdentifierCorpus(CorpusConfig(seed=5)).batch(10, unique_ratio=0.5)


@pytest.mark.unit
def test_a_mixed_batch_contains_the_identifier_types_that_take_the_msearch_path():
    batch = IdentifierCorpus(CorpusConfig(seed=3)).batch(60, pmid_ratio=0.5)
    assert any(identifier.startswith("PMID:") for identifier in batch)
    assert any(identifier.startswith(("PMC:", "doi:")) for identifier in batch)


# --- HARNESS: REPORTING ---
@pytest.mark.unit
def test_report_flags_a_cache_primed_run_so_it_is_not_read_as_cold():
    stage = StageReport(
        label="c=1", concurrency=1, wall_seconds=1.0, samples=[_sample(50.0, 10)] * 10, cache_primed=True
    )
    plan = RunPlan(base_url="https://example.invalid", workload=Workload(unique_ratio=0.0))
    rendered = render_text(RunResult(plan=plan, stages=[stage]))
    assert "primes the backend cache" in rendered
    assert "PASS" in rendered


@pytest.mark.unit
def test_report_flags_a_run_whose_identifiers_mostly_missed():
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=1.0)
    stage.samples.extend([Sample(client_ms=20.0, status=200, server_ms=5, requested=100, found=5, not_found=95)] * 10)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    assert "understates real latency" in render_text(RunResult(plan=plan, stages=[stage]))


@pytest.mark.unit
def test_report_states_both_verdicts_because_they_can_disagree():
    """A network-bound client miss with server headroom is a vantage-point artifact."""
    stage = StageReport(label="c=1", concurrency=1, wall_seconds=1.0, samples=[_sample(400.0, 20)] * 10)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    result = RunResult(plan=plan, stages=[stage])
    rendered = render_text(result)
    assert "server  PASS" in rendered
    assert "client  FAIL" in rendered
    assert slo_met(result, "server")
    assert not slo_met(result, "client")


# --- USER POPULATION MODEL ---
def _stage(label: str, throughput_rps: float, server_ms: int, successes: int, failures: int = 0) -> StageReport:
    samples = [_sample(server_ms + 100.0, server_ms) for _ in range(successes)]
    samples += [Sample(client_ms=2100.0, status=500, requested=100) for _ in range(failures)]
    return StageReport(
        label=label,
        concurrency=1,
        wall_seconds=len(samples) / throughput_rps,
        samples=samples,
    )


@pytest.mark.unit
def test_one_user_offers_far_less_load_than_one_closed_loop_worker():
    """The distinction the user model exists to make explicit.

    A closed-loop worker at 90 ms service time offers about 11 rps. A reader with
    a 30 s think time offers about 0.03 rps — nearly three orders of magnitude
    apart, which is why a concurrency figure cannot be read as a user count.
    """
    model = UserModel(users=1, think_time_seconds=30.0, duration_seconds=60.0)
    assert model.offered_rate_rps == pytest.approx(1 / 30.0)
    assert model.offered_rate_rps < 0.05


@pytest.mark.unit
def test_offered_rate_scales_with_the_population():
    assert UserModel(users=300, think_time_seconds=30.0, duration_seconds=60.0).offered_rate_rps == pytest.approx(10.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "field, value",
    [("users", 0), ("think_time_seconds", 0.0), ("duration_seconds", 0.0), ("catalog_size", 0), ("zipf_exponent", -1)],
)
def test_user_model_rejects_degenerate_configurations(field: str, value: float):
    arguments = {"users": 10, "think_time_seconds": 30.0, "duration_seconds": 60.0}
    arguments[field] = value
    with pytest.raises(ValueError):
        UserModel(**arguments)


@pytest.mark.unit
def test_supported_users_follows_littles_law():
    """46 rps at a 90 ms latency and a 30 s think time is about 1,384 readers."""
    assert supported_users(46.0, 90.0, 30.0) == pytest.approx(46.0 * 30.09)


@pytest.mark.unit
def test_supported_users_counts_service_latency_not_just_think_time():
    """At a short think time the service latency stops being a rounding error."""
    assert supported_users(10.0, 500.0, 1.0) == pytest.approx(15.0)


@pytest.mark.unit
def test_supported_users_is_zero_when_nothing_was_served():
    assert supported_users(0.0, 90.0, 30.0) == 0.0


@pytest.mark.unit
def test_capacity_table_rises_with_think_time():
    rows = capacity_table(46.0, 90.0)
    users = [row["supported_users"] for row in rows]
    assert users == sorted(users)
    assert all(row["requests_per_user_rps"] > 0 for row in rows)


# --- SUSTAINED CEILING ---
@pytest.mark.unit
def test_ceiling_is_the_fastest_passing_stage_not_the_fastest_stage():
    passing = _stage("c=8", throughput_rps=46.0, server_ms=89, successes=100)
    failing = _stage("c=12", throughput_rps=60.0, server_ms=306, successes=100)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload(), ramp=(8, 12))
    assert sustained_ceiling(RunResult(plan=plan, stages=[passing, failing])) is passing


@pytest.mark.unit
def test_a_stage_shedding_load_is_not_capacity_even_with_a_passing_p90():
    """The survivorship trap: failures leave the distribution, improving the p90.

    A stage answering 5% of its load with 500s posts a better p90 than one that
    serves everything slowly, so gating capacity on latency alone would
    recommend a load level at which the service is already erroring.
    """
    shedding = _stage("200u", throughput_rps=87.0, server_ms=100, successes=95, failures=5)
    assert shedding.verdict("server").met
    assert shedding.success_rate < MIN_CEILING_SUCCESS_RATE
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    result = RunResult(plan=plan, stages=[shedding])
    assert sustained_ceiling(result) is None
    assert "not sustained" in render_text(result)


@pytest.mark.unit
def test_success_rate_is_reported_beside_latency():
    stage = _stage("c=1", throughput_rps=10.0, server_ms=50, successes=90, failures=10)
    assert stage.success_rate == pytest.approx(0.90)
    assert stage.as_dict()["success_rate"] == pytest.approx(0.90)


# --- POPULATION REPORTING ---
@pytest.mark.unit
def test_report_says_a_population_that_was_served_bounds_nothing_from_above():
    """A non-saturating run reports the load offered, not the load available."""
    stage = _stage("300u", throughput_rps=10.0, server_ms=47, successes=100)
    model = UserModel(users=300, think_time_seconds=30.0, duration_seconds=60.0)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    rendered = render_text(RunResult(plan=plan, stages=[stage], user_model=model))
    assert "kept up" in rendered
    assert "bounds nothing from above" in rendered


@pytest.mark.unit
def test_report_flags_a_population_whose_offered_rate_went_unmet():
    stage = _stage("200u", throughput_rps=40.0, server_ms=400, successes=100)
    model = UserModel(users=200, think_time_seconds=2.0, duration_seconds=60.0)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    rendered = render_text(RunResult(plan=plan, stages=[stage], user_model=model))
    assert "short of offered" in rendered
    # Server-side latency is over budget here, so the service is the suspect and
    # the load-generator caveat must not be offered as an excuse.
    assert "load generator" not in rendered


@pytest.mark.unit
def test_report_blames_the_generator_only_when_the_service_looks_healthy():
    """A shortfall with a healthy in-handler p90 and no errors is a client limit."""
    stage = _stage("200u", throughput_rps=40.0, server_ms=66, successes=100)
    model = UserModel(users=200, think_time_seconds=2.0, duration_seconds=60.0)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    rendered = render_text(RunResult(plan=plan, stages=[stage], user_model=model))
    assert "short of offered" in rendered
    assert "load generator" in rendered


@pytest.mark.unit
def test_report_always_states_that_user_counts_rest_on_the_think_time_assumption():
    stage = _stage("c=1", throughput_rps=46.0, server_ms=89, successes=100)
    plan = RunPlan(base_url="https://example.invalid", workload=Workload())
    assert "think-time assumption" in render_text(RunResult(plan=plan, stages=[stage]))


# --- SHARED CATALOGUE ---
@pytest.mark.unit
def test_a_skewed_catalogue_concentrates_draws_on_popular_papers():
    """Shared, skewed interest is what a backend cache actually gets to absorb."""
    import collections

    corpus = IdentifierCorpus(CorpusConfig(seed=4))
    catalogue = corpus.seed_catalog(1_000, zipf_exponent=1.0)
    counts = collections.Counter()
    for _ in range(100):
        counts.update(corpus.catalog_batch(100))

    hottest = counts[catalogue[0]]
    coldest = counts[catalogue[-1]]
    assert hottest > coldest
    # The rank-1 paper should appear in nearly every request under classic Zipf.
    assert hottest > 50


@pytest.mark.unit
def test_a_uniform_catalogue_spreads_draws_evenly():
    import collections

    corpus = IdentifierCorpus(CorpusConfig(seed=4))
    catalogue = corpus.seed_catalog(500, zipf_exponent=0.0)
    counts = collections.Counter()
    for _ in range(100):
        counts.update(corpus.catalog_batch(100))
    assert counts[catalogue[0]] < 50


@pytest.mark.unit
def test_catalogue_batches_collapse_repeated_popular_papers():
    """A skewed draw really does repeat, and the endpoint deduplicates too."""
    corpus = IdentifierCorpus(CorpusConfig(seed=8))
    corpus.seed_catalog(20, zipf_exponent=2.0)
    batch = corpus.catalog_batch(100)
    assert len(batch) == len(set(batch))
    assert len(batch) <= 20


@pytest.mark.unit
def test_drawing_from_an_unseeded_catalogue_is_an_error():
    with pytest.raises(ValueError):
        IdentifierCorpus(CorpusConfig(seed=1)).catalog_batch(10)


# --- LIVE DEPLOYMENT ---
@pytest.mark.performance
@requires_live_deployment
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_full_batch_meets_the_slo_on_a_live_deployment(method: str):
    """The CCWG#15 headline case: 100 identifiers in one request, p90 under 150 ms."""
    plan = RunPlan(
        base_url=LIVE_BASE_URL,
        workload=Workload(batch_size=100, method=method),
        concurrency=LIVE_CONCURRENCY,
        requests=LIVE_REQUESTS,
        warmup_requests=10,
        seed=2026,
    )
    result = await run_plan(plan)
    print(render_text(result))

    stage = result.stages[0]
    assert stage.successful, f"no successful responses: {stage.status_counts}"
    assert result.request_id_mismatches == 0, "request_id must round-trip into _meta"

    verdict = stage.verdict(LIVE_BASIS)
    assert verdict.met, (
        f"{LIVE_BASIS}-side p90 was {verdict.p90_ms:.1f} ms against a {SLO_THRESHOLD_MS:g} ms objective "
        f"({verdict.fraction_under_threshold:.1%} of requests under budget)"
    )


@pytest.mark.performance
@requires_live_deployment
@pytest.mark.asyncio(loop_scope="module")
async def test_single_identifier_lookup_is_far_inside_the_budget():
    """The floor case. If one identifier is already tight, the batch case cannot pass."""
    plan = RunPlan(
        base_url=LIVE_BASE_URL,
        workload=Workload(batch_size=1),
        concurrency=1,
        requests=LIVE_REQUESTS,
        warmup_requests=10,
        seed=2026,
    )
    result = await run_plan(plan)
    print(render_text(result))
    assert result.stages[0].verdict("server").met


@pytest.mark.performance
@requires_live_deployment
@pytest.mark.asyncio(loop_scope="module")
async def test_concurrency_ramp_reports_where_the_objective_stops_holding():
    """Records the load-bearing capacity rather than asserting a specific level.

    The concurrency a deployment sustains depends on its replica count and the
    Elasticsearch behind it, so pinning a number here would make this test a
    report of the current CI sizing rather than of the service.
    """
    plan = RunPlan(
        base_url=LIVE_BASE_URL,
        workload=Workload(batch_size=100),
        requests=LIVE_REQUESTS,
        warmup_requests=10,
        seed=2026,
        ramp=(1, 4, 8),
    )
    result = await run_plan(plan)
    print(render_text(result))

    sustained = [stage.concurrency for stage in result.stages if stage.verdict(LIVE_BASIS).met]
    print(f"concurrency levels meeting the {LIVE_BASIS}-side objective: {sustained or 'none'}")
    assert result.stages[0].successful


@pytest.mark.performance
@requires_live_deployment
@pytest.mark.asyncio(loop_scope="module")
async def test_a_simulated_reader_population_is_served_inside_the_budget():
    """The user-facing question: does a population of readers fit under the SLO?

    Asserts on the population being served rather than on a specific user count,
    since the count that fits depends on the deployment's sizing.
    """
    plan = RunPlan(base_url=LIVE_BASE_URL, workload=Workload(batch_size=100), seed=2026, timeout_seconds=30.0)
    model = UserModel(
        users=int(os.environ.get("PUBLICATIONS_LOAD_TEST_USERS", "100")),
        think_time_seconds=float(os.environ.get("PUBLICATIONS_LOAD_TEST_THINK_TIME", "30")),
        duration_seconds=float(os.environ.get("PUBLICATIONS_LOAD_TEST_DURATION", "45")),
    )
    result = await run_user_plan(plan, model)
    print(render_text(result))

    stage = result.stages[0]
    assert stage.samples, "the population issued no requests"
    assert (
        stage.success_rate >= MIN_CEILING_SUCCESS_RATE
    ), f"the service shed load at {model.users} users: {stage.status_counts}"
    assert stage.verdict(LIVE_BASIS).met
