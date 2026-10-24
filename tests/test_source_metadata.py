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
    assert result["biothings"]["sources"]["mygene"] == {
        "build_version": "20260922",
    }
    assert result["elasticsearch"]["connection"] == "ci_forward"
    assert result["elasticsearch"]["sources"]["mygene"] == {
        "index": "gene",
        "indices": {
            "older-index": {"build_version": "20260705"},
            "newer-index": {"build_version": "20260805"},
        },
    }


@pytest.mark.parametrize(
    "biothing_type,expected_name",
    [("gene", "mygene"), ("chem", "mychem"), ("disease", "mydisease"), ("variant", "myvariant")],
)
async def test_biothings_service_names_come_from_client_urls(
    mock_metadata_transport, monkeypatch, biothing_type, expected_name
):
    monkeypatch.setattr(
        source_metadata,
        "ANNOTATOR_CLIENTS",
        {
            "arbitrary_node_type": {
                "client": {"configuration": {"biothing_type": biothing_type}},
                "elasticsearch": {"index": "original_alias"},
            }
        },
    )
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "localhost":
            return httpx.Response(200, json={"concrete_index": {"mappings": {"_meta": {"build_version": "older"}}}})
        return httpx.Response(200, json={"build_version": "current"})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["sources"] == {expected_name: {"build_version": "current"}}
    assert set(result["elasticsearch"]["sources"]) == {expected_name}
    assert result["elasticsearch"]["sources"][expected_name] == {
        "index": "original_alias",
        "indices": {"concrete_index": {"build_version": "older"}},
    }
    assert len(requests) == 2
    assert requests[0].url.host == f"{expected_name}.info"
    assert requests[1].url.path == "/original_alias"


@pytest.mark.parametrize("endpoint", ["hpo", "annotator_extra", "custom_source"])
async def test_endpoint_source_names_are_shared_by_both_backends(mock_metadata_transport, monkeypatch, endpoint):
    monkeypatch.setattr(
        source_metadata,
        "ANNOTATOR_CLIENTS",
        {
            "internal_name": {
                "client": {"configuration": None, "endpoint": endpoint},
                "elasticsearch": {"index": "original_alias"},
            }
        },
    )
    requests = []

    def handler(request):
        requests.append(str(request.url).split("?")[0])
        if request.url.host == "localhost":
            return httpx.Response(200, json={"concrete_index": {"mappings": {"_meta": {"build_version": "older"}}}})
        return httpx.Response(200, json={"build_version": "current"})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert set(result["biothings"]["sources"]) == {endpoint}
    assert set(result["elasticsearch"]["sources"]) == {endpoint}
    assert result["elasticsearch"]["sources"][endpoint]["index"] == "original_alias"
    assert set(requests) == {f"https://custom.example.org/{endpoint}/metadata", "http://localhost:9200/original_alias"}


async def test_es_only_source_can_use_a_client_name_without_querying_the_api(mock_metadata_transport, monkeypatch):
    monkeypatch.setattr(
        source_metadata,
        "ANNOTATOR_CLIENTS",
        {
            "internal_name": {
                "query_backends": ["elasticsearch"],
                "client": {"configuration": {"biothing_type": "gene"}},
                "elasticsearch": {"index": "original_alias"},
            }
        },
    )

    def handler(request):
        assert request.url.host == "localhost"
        assert request.url.path == "/original_alias"
        return httpx.Response(200, json={"concrete_index": {"mappings": {"_meta": {"build_version": "current"}}}})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["sources"] == {}
    assert result["elasticsearch"]["sources"] == {
        "mygene": {"index": "original_alias", "indices": {"concrete_index": {"build_version": "current"}}}
    }


@pytest.mark.parametrize(
    "url,expected_name",
    [
        ("https://customservice.info/v9", "customservice"),
        ("https://proxy.example.org/gene", "gene"),
        ("http://localhost:9000/gene", "gene"),
    ],
)
async def test_custom_client_url_names_have_a_predictable_fallback(
    mock_metadata_transport, two_datasets, url, expected_name
):
    two_datasets["gene"]["client"]["configuration"]["url"] = url
    mock_metadata_transport(lambda request: httpx.Response(200, json={"build_version": "current"}))

    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["sources"][expected_name] == {"build_version": "current"}
    assert result["biothings"]["sources"]["hpo"] == {"build_version": "current"}


async def test_shared_service_names_preserve_all_sources(mock_metadata_transport, two_datasets):
    two_datasets["chem"] = {
        "query_backends": ["biothings"],
        "client": {"configuration": {"biothing_type": "chem", "url": "https://mygene.info/v1"}},
    }
    mock_metadata_transport(lambda request: httpx.Response(200, json={"build_version": request.url.path}))

    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert set(result["biothings"]["sources"]) == {"gene", "chem", "hpo"}
    assert result["biothings"]["sources"]["gene"]["build_version"] == "/v3/metadata"
    assert result["biothings"]["sources"]["chem"]["build_version"] == "/v1/metadata"


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

    assert result["biothings"]["sources"]["mygene"] == {"build_version": None}
    assert result["elasticsearch"]["sources"]["mygene"]["indices"] == {
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

    assert "pubmed" not in result["biothings"]["sources"]
    assert result["elasticsearch"]["sources"]["pubmed"] == {
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

    assert set(result["biothings"]["sources"]) == {"mygene"}
    assert set(result["elasticsearch"]["sources"]) == {"hpo"}
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

    assert result["biothings"]["sources"]["mygene"] == {"error": expected}
    assert result["biothings"]["sources"]["hpo"]["build_version"] == "good"
    assert result["elasticsearch"]["sources"]["mygene"] == {
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
    assert result["biothings"]["sources"]["mygene"]["build_version"] == "good"
    assert result["elasticsearch"]["sources"]["mygene"] == {
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
    assert result["biothings"]["sources"]["mygene"] == {"error": {"code": "timeout"}}
    assert result["biothings"]["sources"]["mychem"]["build_version"] == "good"


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"index": []}, {"index": {"mappings": []}}, {"index": {"mappings": {"_meta": []}}}],
)
async def test_malformed_es_metadata_is_reported(mock_metadata_transport, two_datasets, payload):
    def handler(request):
        return httpx.Response(200, json=payload if request.url.host == "localhost" else {})

    mock_metadata_transport(handler)
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["elasticsearch"]["sources"]["mygene"]["error"] == {"code": "invalid_metadata"}


async def test_missing_client_type_never_triggers_sdk_discovery(mock_metadata_transport, two_datasets, monkeypatch):
    two_datasets["gene"]["client"]["configuration"] = {"url": "https://private.example.org"}

    def no_client_discovery(*args, **kwargs):
        pytest.fail("An untyped client must not trigger SDK discovery")

    monkeypatch.setattr(source_metadata.biothings_client, "get_async_client", no_client_discovery)
    mock_metadata_transport(lambda request: httpx.Response(200, json={}))
    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["biothings"]["sources"]["gene"] == {"error": {"code": "configuration_error"}}


async def test_malformed_dataset_configuration_is_isolated(mock_metadata_transport, two_datasets):
    two_datasets["gene"]["elasticsearch"] = None
    mock_metadata_transport(lambda request: httpx.Response(200, json={"build_version": "good"}))

    result = await source_metadata.collect_backend_metadata("https://custom.example.org", "local")

    assert result["elasticsearch"]["sources"]["mygene"] == {
        "index": None,
        "error": {"code": "configuration_error"},
    }
    assert result["biothings"]["sources"]["mygene"]["build_version"] == "good"
