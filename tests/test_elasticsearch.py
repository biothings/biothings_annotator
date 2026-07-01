"""
Exercises the Elasticsearch annotator backend.
"""

import json

import httpx
import pytest

from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.elasticsearch import ElasticsearchAnnotatorClient
from biothings_annotator.annotator.settings import ANNOTATOR_CLIENTS, ELASTICSEARCH_CONNECTIONS, QUERY_BACKEND_ENV
from biothings_annotator.annotator.utils import get_elasticsearch_client, get_elasticsearch_connection


def test_annotator_can_switch_query_backend_by_assignment(monkeypatch):
    monkeypatch.delenv(QUERY_BACKEND_ENV, raising=False)
    monkeypatch.delenv("ELASTICSEARCH_CONNECTION", raising=False)

    annotator = Annotator()
    assert annotator.query_backend == "biothings"
    assert annotator.elasticsearch_connection == "ci"

    annotator.query_backend = "elasticsearch"
    assert annotator.query_backend == "elasticsearch"
    assert annotator.elasticsearch_connection == "ci"

    annotator.elasticsearch_connection = "local"
    assert annotator.elasticsearch_connection == "local"

    annotator.query_backend = "biothings"
    annotator.api_host = "https://biothings.test.example.org"
    assert annotator.query_backend == "biothings"
    assert annotator.api_host == "https://biothings.test.example.org"


def test_annotator_uses_query_backend_environment(monkeypatch):
    monkeypatch.setenv(QUERY_BACKEND_ENV, " Elasticsearch ")

    annotator = Annotator()

    assert annotator.query_backend == "elasticsearch"


def test_annotator_strips_elasticsearch_connection_environment(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_CONNECTION", " ci_local_forward ")

    annotator = Annotator()

    assert annotator.elasticsearch_connection == "ci_local_forward"


@pytest.mark.asyncio
async def test_elasticsearch_querymany_formats_biothings_style_hits():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/gene/_msearch"

        lines = [json.loads(line) for line in request.content.decode().splitlines()]
        assert lines[1]["_source"] == ["symbol"]
        assert lines[1]["query"]["bool"]["minimum_should_match"] == 1

        return httpx.Response(
            200,
            json={
                "responses": [
                    {
                        "hits": {
                            "hits": [
                                {
                                    "_id": "1017",
                                    "_score": 1.0,
                                    "_source": {"symbol": "CDK2"},
                                }
                            ]
                        }
                    },
                    {"hits": {"hits": []}},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient("http://localhost:9200", "gene", http_client=http_client)
        result = await client.querymany(["1017", "0"], scopes=["entrezgene"], fields=["symbol"])

    assert result == [
        {"symbol": "CDK2", "_id": "1017", "_score": 1.0, "query": "1017"},
        {"query": "0", "notfound": True},
    ]


@pytest.mark.asyncio
async def test_elasticsearch_client_supports_configured_headers():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {
                "host": request.headers["host"],
                "content_type": request.headers["content-type"],
            }
        )
        return httpx.Response(200, json={"responses": [{"hits": {"hits": []}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient(
            "http://localhost:9200",
            "gene",
            headers={"Host": "core-components-es.ci.transltr.io"},
            http_client=http_client,
        )
        result = await client.querymany(["1017"], scopes="_id", fields=["symbol"])

    assert requests == [
        {
            "host": "core-components-es.ci.transltr.io",
            "content_type": "application/x-ndjson",
        }
    ]
    assert result == [{"query": "1017", "notfound": True}]


def test_elasticsearch_connection_config_supports_local_forwarded_ci_host():
    expected_connection = {
        "host": "http://localhost:9200",
        "headers": {"Host": "core-components-es.ci.transltr.io"},
    }
    assert ELASTICSEARCH_CONNECTIONS["ci_forward"] is ELASTICSEARCH_CONNECTIONS["ci_local_forward"]
    assert get_elasticsearch_connection("ci_local_forward") == expected_connection
    assert get_elasticsearch_connection("ci_forward") == expected_connection


def test_elasticsearch_client_uses_named_connection_config():
    elasticsearch_settings = ANNOTATOR_CLIENTS["gene"]["elasticsearch"]
    original_instance = elasticsearch_settings.get("instance")
    try:
        elasticsearch_settings["instance"] = None

        ci_local_forward_client = get_elasticsearch_client("gene", "ci_local_forward")
        assert ci_local_forward_client.host == "http://localhost:9200"
        assert ci_local_forward_client.headers == {"Host": "core-components-es.ci.transltr.io"}
        assert get_elasticsearch_client("gene", "ci_local_forward") is ci_local_forward_client

        local_client = get_elasticsearch_client("gene", "local")
        assert local_client is not ci_local_forward_client
        assert local_client.host == "http://localhost:9200"
        assert local_client.headers == {}
    finally:
        elasticsearch_settings["instance"] = original_instance


@pytest.mark.asyncio
async def test_elasticsearch_client_reuses_owned_http_client():
    client = ElasticsearchAnnotatorClient("http://localhost:9200", "gene")

    first_http_client = client._http_client
    second_http_client = client._http_client

    assert first_http_client is second_http_client

    await client.aclose()
    assert client._owned_http_client is None


@pytest.mark.asyncio
async def test_elasticsearch_querymany_accepts_size_kwarg():
    requested_sizes = []

    async def handler(request: httpx.Request) -> httpx.Response:
        lines = [json.loads(line) for line in request.content.decode().splitlines()]
        requested_sizes.extend(line["size"] for line in lines if "query" in line)

        return httpx.Response(
            200,
            json={
                "responses": [
                    {
                        "hits": {
                            "hits": [
                                {
                                    "_id": "1017",
                                    "_source": {"symbol": "CDK2"},
                                }
                            ]
                        }
                    },
                    {
                        "hits": {
                            "hits": [
                                {
                                    "_id": "1018",
                                    "_source": {"symbol": "CDK3"},
                                }
                            ]
                        }
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient("http://localhost:9200", "gene", http_client=http_client)
        result = await client.querymany(["1017", "1018"], scopes=["entrezgene"], fields=["symbol"], size=1000)

    assert requested_sizes == [1000, 1000]
    assert result == [
        {"symbol": "CDK2", "_id": "1017", "query": "1017"},
        {"symbol": "CDK3", "_id": "1018", "query": "1018"},
    ]


@pytest.mark.asyncio
async def test_elasticsearch_querymany_batches_input_terms():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        lines = [json.loads(line) for line in request.content.decode().splitlines()]
        query_ids = [
            line["query"]["bool"]["should"][0]["ids"]["values"][0]
            for line in lines
            if "query" in line
        ]
        requests.append(query_ids)

        return httpx.Response(
            200,
            json={
                "responses": [
                    {
                        "hits": {
                            "hits": [
                                {
                                    "_id": query_id,
                                    "_source": {"name": f"node-{query_id}"},
                                }
                            ]
                        }
                    }
                    for query_id in query_ids
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient(
            "http://localhost:9200",
            "gene",
            query_batch_size=2,
            http_client=http_client,
        )
        result = await client.querymany(["1", "2", "3"], scopes="_id", fields=["name"])

    assert requests == [["1", "2"], ["3"]]
    assert result == [
        {"name": "node-1", "_id": "1", "query": "1"},
        {"name": "node-2", "_id": "2", "query": "2"},
        {"name": "node-3", "_id": "3", "query": "3"},
    ]


@pytest.mark.asyncio
async def test_elasticsearch_query_accepts_size_and_skip():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "took": 7,
                "hits": {
                    "total": {"value": 2302, "relation": "eq"},
                    "max_score": 138.9,
                    "hits": [
                        {
                            "_id": "1017",
                            "_score": 138.9,
                            "_source": {"symbol": "CDK2"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient("http://localhost:9200", "gene", http_client=http_client)
        result = await client.query("CDK2", fields=["symbol"], size=25, skip=10)

    assert requests == [
        {
            "size": 25,
            "_source": ["symbol"],
            "query": {"query_string": {"query": "CDK2"}},
            "from": 10,
        }
    ]
    assert result == {
        "took": 7,
        "total": 2302,
        "max_score": 138.9,
        "hits": [{"symbol": "CDK2", "_id": "1017", "_score": 138.9}],
    }


@pytest.mark.asyncio
async def test_elasticsearch_query_fetch_all_uses_point_in_time():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content) if request.content else {}
        requests.append({"method": request.method, "path": request.url.path, "body": content})
        if request.url.path == "/annotator_extra/_pit":
            return httpx.Response(200, json={"id": "pit-1"})
        if request.url.path == "/_search":
            hits = [
                {
                    "_id": "A01",
                    "_source": {"atc": {"code": "A01", "name": "Stomatological preparations"}},
                    "sort": [1],
                },
                {
                    "_id": "A02",
                    "_source": {"atc": {"code": "A02", "name": "Drugs for acid related disorders"}},
                    "sort": [2],
                },
            ]
            if "search_after" in content:
                hits = [
                    {
                        "_id": "A03",
                        "_source": {"atc": {"code": "A03", "name": "Drugs for functional gastrointestinal disorders"}},
                        "sort": [3],
                    }
                ]
            return httpx.Response(200, json={"pit_id": "pit-2", "hits": {"hits": hits}})
        if request.url.path == "/_pit":
            return httpx.Response(200, json={"succeeded": True, "num_freed": 1})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient("http://localhost:9200", "annotator_extra", http_client=http_client)
        result_iterator = await client.query("_exists_:atc.code", fields="atc.code,atc.name", fetch_all=True, size=2)
        result = [doc async for doc in result_iterator]

    assert requests[0] == {"method": "POST", "path": "/annotator_extra/_pit", "body": {}}
    assert requests[1]["body"]["query"] == {"exists": {"field": "atc.code"}}
    assert requests[1]["body"]["pit"] == {"id": "pit-1", "keep_alive": "1m"}
    assert requests[1]["body"]["size"] == 2
    assert requests[2]["body"]["search_after"] == [2]
    assert requests[-1] == {"method": "DELETE", "path": "/_pit", "body": {"id": "pit-2"}}
    assert result == [
        {"atc": {"code": "A01", "name": "Stomatological preparations"}, "_id": "A01"},
        {"atc": {"code": "A02", "name": "Drugs for acid related disorders"}, "_id": "A02"},
        {"atc": {"code": "A03", "name": "Drugs for functional gastrointestinal disorders"}, "_id": "A03"},
    ]


@pytest.mark.asyncio
async def test_elasticsearch_query_fetch_all_falls_back_when_point_in_time_is_unavailable():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content) if request.content else {}
        requests.append({"method": request.method, "path": request.url.path, "body": content})
        if request.url.path == "/annotator_extra/_pit":
            return httpx.Response(404, json={"error": "no handler found for uri"})

        hits = [
            {
                "_id": "A01",
                "_source": {"atc": {"code": "A01", "name": "Stomatological preparations"}},
            }
        ]
        if content.get("from", 0) > 0:
            hits = []
        return httpx.Response(200, json={"hits": {"hits": hits}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient("http://localhost:9200", "annotator_extra", http_client=http_client)
        result_iterator = await client.query("_exists_:atc.code", fields="atc.code,atc.name", fetch_all=True)
        result = [doc async for doc in result_iterator]

    assert requests[0]["path"] == "/annotator_extra/_pit"
    assert requests[1]["path"] == "/annotator_extra/_search"
    assert requests[1]["body"]["from"] == 0
    assert requests[1]["body"]["size"] == 1000
    assert result == [{"atc": {"code": "A01", "name": "Stomatological preparations"}, "_id": "A01"}]


@pytest.mark.asyncio
async def test_query_annotations_uses_configured_query_client(monkeypatch):
    annotator = Annotator()
    annotator.query_backend = "elasticsearch"
    annotator.elasticsearch_connection = "ci"
    calls = []

    class FakeQueryClient:
        async def querymany(self, query_list, scopes, fields):
            calls.append({"query_list": query_list, "scopes": scopes, "fields": fields})
            return [{"query": "1017", "_id": "1017", "symbol": "CDK2"}]

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: calls.append(
            {
                "node_type": node_type,
                "query_backend": query_backend,
                "api_host": api_host,
                "elasticsearch_connection": elasticsearch_connection,
            }
        )
        or FakeQueryClient(),
    )

    result = await annotator.query_annotations("gene", ["1017"], fields=["symbol"])

    assert result == {"1017": [{"query": "1017", "_id": "1017", "symbol": "CDK2"}]}
    assert calls == [
        {
            "node_type": "gene",
            "query_backend": "elasticsearch",
            "api_host": annotator.api_host,
            "elasticsearch_connection": "ci",
        },
        {
            "query_list": ["1017"],
            "scopes": ["entrezgene", "ensemblgene", "uniprot", "accession", "retired"],
            "fields": ["symbol"],
        }
    ]


@pytest.mark.asyncio
async def test_query_annotations_keeps_biothings_default(monkeypatch):
    annotator = Annotator()
    annotator.query_backend = "biothings"
    annotator.api_host = "https://biothings.example.org"

    class FakeQueryClient:
        async def querymany(self, query_list, scopes, fields):
            return [{"query": "1017", "_id": "1017"}]

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: FakeQueryClient(),
    )

    result = await annotator.query_annotations("gene", ["1017"])

    assert result == {"1017": [{"query": "1017", "_id": "1017"}]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_append_extra_annotations_skips_missing_query_client(monkeypatch):
    annotator = Annotator()
    node_d = {"CHEMBL.COMPOUND:CHEMBL123": [{"query": "CHEMBL123", "_id": "CHEMBL123"}]}

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: None,
    )

    await annotator.append_extra_annotations(node_d)

    assert node_d == {"CHEMBL.COMPOUND:CHEMBL123": [{"query": "CHEMBL123", "_id": "CHEMBL123"}]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_append_extra_annotations_skips_empty_subset(monkeypatch):
    annotator = Annotator()
    node_d = {"NCBIGene:1017": [{"query": "1017", "_id": "1017"}]}

    def fail_get_query_client(node_type, query_backend, api_host, elasticsearch_connection):
        raise AssertionError("empty extra subset should not request a query client")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        fail_get_query_client,
    )

    await annotator.append_extra_annotations(node_d, node_id_subset=[])

    assert node_d == {"NCBIGene:1017": [{"query": "1017", "_id": "1017"}]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_append_extra_annotations_skips_querymany_failure(monkeypatch):
    annotator = Annotator()
    node_d = {"CHEMBL.COMPOUND:CHEMBL123": [{"query": "CHEMBL123", "_id": "CHEMBL123"}]}

    class FailingExtraClient:
        async def querymany(self, query_list, scopes, fields):
            raise RuntimeError("extra annotations unavailable")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: FailingExtraClient(),
    )

    await annotator.append_extra_annotations(node_d)

    assert node_d == {"CHEMBL.COMPOUND:CHEMBL123": [{"query": "CHEMBL123", "_id": "CHEMBL123"}]}
