"""
Exercises the Elasticsearch annotator backend.
"""

import json

import httpx
import pytest

from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.elasticsearch import ElasticsearchAnnotatorClient


def test_annotator_can_switch_query_backend_by_assignment():
    annotator = Annotator()

    annotator.query_backend = "elasticsearch"
    annotator.elasticsearch_host = "http://localhost:9300"
    assert annotator.query_backend == "elasticsearch"
    assert annotator.elasticsearch_host == "http://localhost:9300"

    annotator.query_backend = "biothings"
    annotator.api_host = "https://biothings.test.example.org"
    assert annotator.query_backend == "biothings"
    assert annotator.api_host == "https://biothings.test.example.org"


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
async def test_elasticsearch_query_fetch_all_supports_exists_query():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        hits = [
            {
                "_id": "A01",
                "_source": {"atc": {"code": "A01", "name": "Stomatological preparations"}},
            }
        ]
        if len(requests) > 1:
            hits = []

        return httpx.Response(200, json={"hits": {"hits": hits}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ElasticsearchAnnotatorClient("http://localhost:9200", "annotator_extra", http_client=http_client)
        result_iterator = await client.query("_exists_:atc.code", fields="atc.code,atc.name", fetch_all=True)
        result = [doc async for doc in result_iterator]

    assert requests[0]["query"] == {"exists": {"field": "atc.code"}}
    assert result == [{"atc": {"code": "A01", "name": "Stomatological preparations"}, "_id": "A01"}]


@pytest.mark.asyncio
async def test_query_annotations_uses_configured_query_client(monkeypatch):
    annotator = Annotator()
    annotator.query_backend = "elasticsearch"
    annotator.elasticsearch_host = "http://localhost:9300"
    calls = []

    class FakeQueryClient:
        async def querymany(self, query_list, scopes, fields):
            calls.append({"query_list": query_list, "scopes": scopes, "fields": fields})
            return [{"query": "1017", "_id": "1017", "symbol": "CDK2"}]

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_host: FakeQueryClient(),
    )

    result = await annotator.query_annotations("gene", ["1017"], fields=["symbol"])

    assert result == {"1017": [{"query": "1017", "_id": "1017", "symbol": "CDK2"}]}
    assert calls == [
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
        lambda node_type, query_backend, api_host, elasticsearch_host: FakeQueryClient(),
    )

    result = await annotator.query_annotations("gene", ["1017"])

    assert result == {"1017": [{"query": "1017", "_id": "1017"}]}
