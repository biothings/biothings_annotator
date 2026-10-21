"""Source metadata reports distinct backend builds without affecting health."""

import asyncio

import httpx
import pytest

from biothings_annotator.annotator import source_metadata


pytestmark = pytest.mark.unit


@pytest.fixture
def mock_metadata_transport(monkeypatch):
    async_client = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(
            source_metadata.httpx,
            "AsyncClient",
            lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return install


@pytest.fixture
def two_datasets(monkeypatch):
    datasets = {
        "gene": {
            "client": {"configuration": {"biothing_type": "gene"}, "endpoint": None},
            "elasticsearch": {"index": "gene"},
        },
        "phenotype": {
            "client": {"configuration": None, "endpoint": "hpo"},
            "elasticsearch": {"index": "hpo"},
        },
    }
    monkeypatch.setattr(source_metadata, "ANNOTATOR_CLIENTS", datasets)
    return datasets


async def test_collects_actual_client_urls_and_distinct_backend_build_versions(
    mock_metadata_transport, two_datasets, monkeypatch
):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "localhost":
            assert request.headers["host"] == "core-components-es.ci.transltr.io"
            assert request.url.params["filter_path"] == "*.mappings._meta.build_version,*.settings.index.uuid"
            return httpx.Response(
                200,
                json={
                    "older-index": {
                        "mappings": {"_meta": {"build_version": "20260705", "src": {"entrez": {"version": "old"}}}}
                    },
                    "newer-index": {
                        "mappings": {"_meta": {"build_version": "20260805", "src": {"entrez": {"version": "new"}}}}
                    },
                },
            )
        assert "core-components-es" not in request.headers["host"]
        return httpx.Response(
            200,
            json={
                "build_version": "20260922",
                "src": {"entrez": {"version": "current"}, "unknown": {}, "numeric": {"version": 42}},
            },
        )

    def no_synchronous_network(*args, **kwargs):
        pytest.fail("Metadata discovery must not issue synchronous network requests")

    monkeypatch.setattr(httpx, "get", no_synchronous_network)
    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org/", "ci_forward")

    assert {str(request.url).split("?")[0] for request in requests} == {
        "https://mygene.info/v3/metadata",
        "https://custom.example.org/hpo/metadata",
        "http://localhost:9200/gene",
        "http://localhost:9200/hpo",
    }
    assert result["biothings"]["datasets"]["gene"] == {
        "build_version": "20260922",
    }
    assert result["elasticsearch"]["connection"] == "ci_forward"
    assert result["elasticsearch"]["datasets"]["gene"] == {
        "index": "gene",
        "indices": {
            "older-index": {"build_version": "20260705"},
            "newer-index": {"build_version": "20260805"},
        },
    }


async def test_retains_indices_with_no_metadata_without_inferring_versions(mock_metadata_transport, two_datasets):
    def handler(request):
        payload = (
            {"gene_20260922": {"settings": {"index": {"uuid": "not-a-version"}}}}
            if request.url.host == "localhost"
            else {}
        )
        return httpx.Response(200, json=payload)

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["datasets"]["gene"] == {"build_version": None}
    assert result["elasticsearch"]["datasets"]["gene"]["indices"] == {
        "gene_20260922": {"build_version": None}
    }


async def test_pubmed_metadata_uses_elasticsearch_only(mock_metadata_transport):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "localhost":
            return httpx.Response(
                200,
                json={"pubmed-build": {"mappings": {"_meta": {"build_version": "20260814"}}}},
            )
        assert request.url.path != "/pubmed/metadata"
        return httpx.Response(200, json={"build_version": "other-source"})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert "pubmed" not in result["biothings"]["datasets"]
    assert result["elasticsearch"]["datasets"]["pubmed"] == {
        "index": "annotator-pubmed",
        "indices": {"pubmed-build": {"build_version": "20260814"}},
    }
    assert any(request.url.host == "localhost" and request.url.path == "/annotator-pubmed" for request in requests)
    assert all(request.url.path != "/pubmed/metadata" for request in requests)


async def test_dataset_capabilities_filter_each_backend(mock_metadata_transport, two_datasets):
    two_datasets["gene"]["query_backends"] = ["biothings"]
    two_datasets["phenotype"]["query_backends"] = ["elasticsearch"]
    requests = []

    def handler(request):
        requests.append(str(request.url).split("?")[0])
        if request.url.host == "localhost":
            return httpx.Response(200, json={"hpo-build": {"mappings": {"_meta": {"build_version": "hpo"}}}})
        return httpx.Response(200, json={"build_version": "gene"})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert set(result["biothings"]["datasets"]) == {"gene"}
    assert set(result["elasticsearch"]["datasets"]) == {"phenotype"}
    assert set(requests) == {"https://mygene.info/v3/metadata", "http://localhost:9200/hpo"}


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("http", {"code": "http_error", "http_status": 503}),
        ("connection", {"code": "connection_error"}),
        ("timeout", {"code": "timeout"}),
        ("json", {"code": "invalid_metadata"}),
        ("shape", {"code": "invalid_metadata"}),
    ],
)
async def test_individual_errors_are_sanitized_and_other_sources_survive(
    mock_metadata_transport, two_datasets, failure, expected
):
    def handler(request):
        if request.url.host == "mygene.info":
            if failure == "http":
                return httpx.Response(503, text="private credentials and upstream diagnostics")
            if failure == "connection":
                raise httpx.ConnectError("private connection URL", request=request)
            if failure == "timeout":
                raise httpx.ReadTimeout("private connection URL", request=request)
            if failure == "json":
                return httpx.Response(200, text="private non-JSON response")
            return httpx.Response(200, json=["malformed"])
        if request.url.host == "localhost":
            return httpx.Response(404, json={"error": "sensitive index diagnostics"})
        return httpx.Response(200, json={"build_version": "good", "src": {}})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["datasets"]["gene"] == {"error": expected}
    assert result["biothings"]["datasets"]["phenotype"]["build_version"] == "good"
    assert result["elasticsearch"]["datasets"]["gene"] == {
        "index": "gene",
        "error": {"code": "http_error", "http_status": 404},
    }
    assert "private" not in repr(result)
    assert "sensitive" not in repr(result)


async def test_invalid_es_connection_does_not_prevent_biothings_metadata(mock_metadata_transport, two_datasets):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"build_version": "good"})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "missing")

    assert len(requests) == 2
    assert result["biothings"]["datasets"]["gene"]["build_version"] == "good"
    assert result["elasticsearch"]["datasets"]["gene"] == {
        "index": "gene",
        "error": {"code": "configuration_error"},
    }


async def test_all_datasets_fetch_concurrently_with_total_deadlines(mock_metadata_transport, monkeypatch):
    started = []
    cancelled = []
    all_started = asyncio.Event()
    expected_requests = sum(
        backend in settings.get("query_backends", source_metadata.SUPPORTED_QUERY_BACKENDS)
        for settings in source_metadata.ANNOTATOR_CLIENTS.values()
        for backend in source_metadata.SUPPORTED_QUERY_BACKENDS
    )

    async def handler(request):
        started.append(str(request.url))
        if len(started) == expected_requests:
            all_started.set()
        await all_started.wait()
        if request.url.host == "mygene.info":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(str(request.url))
                raise
        if request.url.host == "localhost":
            return httpx.Response(200, json={"concrete-index": {"mappings": {"_meta": {"build_version": "good"}}}})
        return httpx.Response(200, json={"build_version": "good"})

    monkeypatch.setattr(source_metadata, "SOURCE_METADATA_TIMEOUT", 0.1)
    mock_metadata_transport(handler)
    result = await asyncio.wait_for(
        source_metadata.collect_backend_metadata("https://custom.example.org", "local"), timeout=2
    )

    assert len(started) == expected_requests
    assert len(cancelled) == 1
    assert result["biothings"]["datasets"]["gene"] == {"error": {"code": "timeout"}}
    assert result["biothings"]["datasets"]["chem"]["build_version"] == "good"


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"index": []}, {"index": {"mappings": []}}, {"index": {"mappings": {"_meta": []}}}],
)
async def test_malformed_es_metadata_is_reported(mock_metadata_transport, two_datasets, payload):
    def handler(request):
        return httpx.Response(200, json=payload if request.url.host == "localhost" else {})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["elasticsearch"]["datasets"]["gene"]["error"] == {"code": "invalid_metadata"}


async def test_missing_client_type_never_triggers_sdk_discovery(mock_metadata_transport, two_datasets, monkeypatch):
    two_datasets["gene"]["client"]["configuration"] = {"url": "https://private.example.org"}

    def no_client_discovery(*args, **kwargs):
        pytest.fail("An untyped client must not trigger SDK discovery")

    monkeypatch.setattr(source_metadata.biothings_client, "get_async_client", no_client_discovery)
    mock_metadata_transport(lambda request: httpx.Response(200, json={}))
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["datasets"]["gene"] == {"error": {"code": "configuration_error"}}


async def test_malformed_dataset_configuration_is_isolated(mock_metadata_transport, two_datasets):
    two_datasets["gene"]["elasticsearch"] = None
    mock_metadata_transport(lambda request: httpx.Response(200, json={"build_version": "good"}))

    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["elasticsearch"]["datasets"]["gene"] == {
        "index": None,
        "error": {"code": "configuration_error"},
    }
    assert result["biothings"]["datasets"]["gene"]["build_version"] == "good"
