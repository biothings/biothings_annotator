"""Tests for the dedicated PubMed document metadata fast path."""

import asyncio
import re

import pytest
import sanic

from biothings_annotator.annotator.document_metadata import (
    DocumentMetadataService,
    format_publication_metadata,
)
from biothings_annotator.application.views.document_metadata import validate_publication_ids


PMID = "PMID:30690000"
MISSING_PMID = "PMID:82374"
PUBMED_METADATA = {
    "journal": {"name": "European journal of pharmacology", "abbr": "Eur J Pharmacol"},
    "title": "Example article",
    "vol": "847",
    "iss": "",
    "pub_date": "2019-03-15",
    "abstract": "Example abstract",
}
FORMATTED_METADATA = {
    "journal_name": "European journal of pharmacology",
    "journal_abbrev": "Eur J Pharmacol",
    "article_title": "Example article",
    "volume": "847",
    "issue": "",
    "pub_year": "2019",
    "pub_month": "Mar",
    "pub_day": "15",
    "abstract": "Example abstract",
}


@pytest.mark.unit
def test_format_publication_metadata_uses_empty_strings_and_date_precision():
    assert format_publication_metadata(PUBMED_METADATA) == FORMATTED_METADATA
    assert format_publication_metadata({"pub_date": "2026-07"}) == {
        "journal_name": "",
        "journal_abbrev": "",
        "article_title": "",
        "volume": "",
        "issue": "",
        "pub_year": "2026",
        "pub_month": "Jul",
        "pub_day": "",
        "abstract": "",
    }


@pytest.mark.unit
def test_parse_publication_ids_accepts_one_hundred_and_preserves_order():
    publication_ids = [f"PMID:{index}" for index in range(1, 101)]

    assert validate_publication_ids(publication_ids) == publication_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_document_metadata_service_uses_only_pubmed_mget(monkeypatch):
    calls = []

    class FakePubMedClient:
        async def mget(self, query_list, fields):
            calls.append({"query_list": query_list, "fields": fields})
            return [
                {"query": PMID, "_id": PMID, "pubmed": PUBMED_METADATA},
                {"query": MISSING_PMID, "notfound": True},
            ]

    def get_fake_client(node_type, elasticsearch_connection):
        calls.append(
            {
                "node_type": node_type,
                "elasticsearch_connection": elasticsearch_connection,
            }
        )
        return FakePubMedClient()

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        get_fake_client,
    )

    service = DocumentMetadataService(elasticsearch_connection="ci")
    results, not_found = await service.get_publications([PMID, MISSING_PMID])

    assert calls == [
        {"node_type": "pubmed", "elasticsearch_connection": "ci"},
        {"query_list": [PMID, MISSING_PMID], "fields": ["pubmed"]},
    ]
    assert results == {PMID: FORMATTED_METADATA}
    assert not_found == [MISSING_PMID]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_document_metadata_service_enforces_short_request_deadline(monkeypatch):
    class SlowPubMedClient:
        async def mget(self, query_list, fields):
            del query_list, fields
            await asyncio.Event().wait()

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: SlowPubMedClient(),
    )

    service = DocumentMetadataService(elasticsearch_connection="ci", request_timeout=0.001)
    with pytest.raises(asyncio.TimeoutError):
        await service.get_publications([PMID])


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publications_endpoint_returns_legacy_envelope_and_deduplicates(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    calls = []

    async def get_publications(self, publication_ids):
        del self
        calls.append(publication_ids)
        return {PMID: FORMATTED_METADATA}, [MISSING_PMID]

    monkeypatch.setattr(DocumentMetadataService, "get_publications", get_publications)

    _, response = await test_annotator.asgi_client.get(
        f"/publications?pubids={PMID},{MISSING_PMID},{PMID}&request_id=request-123"
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert calls == [[PMID, MISSING_PMID]]
    assert response.json["results"] == {PMID: FORMATTED_METADATA}
    assert response.json["not_found"] == [MISSING_PMID]
    assert response.json["_meta"]["n_results"] == 1
    assert response.json["_meta"]["request_id"] == "request-123"
    assert isinstance(response.json["_meta"]["processing_time_ms"], int)
    assert response.json["_meta"]["processing_time_ms"] >= 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", response.json["_meta"]["timestamp"])


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publication_path_endpoint_returns_one_publication(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    calls = []

    async def get_publications(self, publication_ids):
        del self
        calls.append(publication_ids)
        return {PMID: FORMATTED_METADATA}, []

    monkeypatch.setattr(DocumentMetadataService, "get_publications", get_publications)

    _, response = await test_annotator.asgi_client.get(
        f"/publications/{PMID}?request_id=path-request"
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert calls == [[PMID]]
    assert response.json["results"] == {PMID: FORMATTED_METADATA}
    assert response.json["not_found"] == []
    assert response.json["_meta"]["n_results"] == 1
    assert response.json["_meta"]["request_id"] == "path-request"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publications_post_accepts_object_and_bare_list_bodies(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    calls = []

    async def get_publications(self, publication_ids):
        del self
        calls.append(publication_ids)
        results = {publication_id: FORMATTED_METADATA for publication_id in publication_ids if publication_id == PMID}
        not_found = [publication_id for publication_id in publication_ids if publication_id != PMID]
        return results, not_found

    monkeypatch.setattr(DocumentMetadataService, "get_publications", get_publications)

    _, object_response = await test_annotator.asgi_client.post(
        "/publications?request_id=query-request",
        json={
            "ids": [PMID, MISSING_PMID, PMID],
            "request_id": "body-request",
        },
    )
    _, list_response = await test_annotator.asgi_client.post(
        "/publications?request_id=list-request",
        json=[MISSING_PMID, PMID],
    )

    assert calls == [[PMID, MISSING_PMID], [MISSING_PMID, PMID]]
    assert object_response.status_code == 200
    assert object_response.content_type == "application/json"
    assert object_response.json["results"] == {PMID: FORMATTED_METADATA}
    assert object_response.json["not_found"] == [MISSING_PMID]
    assert object_response.json["_meta"]["request_id"] == "body-request"
    assert list_response.status_code == 200
    assert list_response.content_type == "application/json"
    assert list_response.json["results"] == {PMID: FORMATTED_METADATA}
    assert list_response.json["not_found"] == [MISSING_PMID]
    assert list_response.json["_meta"]["request_id"] == "list-request"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "query, message",
    [
        ("", "pubids query parameter is required"),
        ("?pubids=", "pubids query parameter is required"),
        (f"?pubids={PMID},", "without empty values"),
        ("?pubids=PMC:12345", "Only PMID identifiers"),
        ("?pubids=PMID:0", "Only PMID identifiers"),
        ("?pubids=PMID:not-a-number", "Only PMID identifiers"),
        (
            "?pubids=" + ",".join(f"PMID:{index}" for index in range(1, 102)),
            "maximum of 100",
        ),
    ],
)
async def test_publications_endpoint_rejects_invalid_requests_before_lookup(
    test_annotator: sanic.Sanic,
    monkeypatch,
    query,
    message,
):
    async def fail_lookup(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Invalid requests must not query Elasticsearch")

    monkeypatch.setattr(DocumentMetadataService, "get_publications", fail_lookup)

    _, response = await test_annotator.asgi_client.get(f"/publications{query}")

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert message in response.json["message"]


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "publication_id, message",
    [
        ("PMC:12345", "Only PMID identifiers"),
        ("PMID:0", "Only PMID identifiers"),
        ("PMID:not-a-number", "Only PMID identifiers"),
    ],
)
async def test_publication_path_endpoint_rejects_invalid_ids_before_lookup(
    test_annotator: sanic.Sanic,
    monkeypatch,
    publication_id,
    message,
):
    async def fail_lookup(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Invalid requests must not query Elasticsearch")

    monkeypatch.setattr(DocumentMetadataService, "get_publications", fail_lookup)

    _, response = await test_annotator.asgi_client.get(f"/publications/{publication_id}")

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json["endpoint"] == "/publications"
    assert message in response.json["message"]


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "body, message",
    [
        ({}, "At least one publication ID is required"),
        ({"ids": []}, "At least one publication ID is required"),
        ({"ids": PMID}, "At least one publication ID is required"),
        ({"ids": ["PMC:12345"]}, "Only PMID identifiers"),
        ({"ids": [PMID, 42]}, "Only PMID identifiers"),
        ({"ids": [PMID], "request_id": 42}, "request_id must be a string"),
        (
            {"ids": [f"PMID:{index}" for index in range(1, 102)]},
            "maximum of 100",
        ),
    ],
)
async def test_publications_post_rejects_invalid_bodies_before_lookup(
    test_annotator: sanic.Sanic,
    monkeypatch,
    body,
    message,
):
    async def fail_lookup(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Invalid requests must not query Elasticsearch")

    monkeypatch.setattr(DocumentMetadataService, "get_publications", fail_lookup)

    _, response = await test_annotator.asgi_client.post("/publications", json=body)

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json["endpoint"] == "/publications"
    assert message in response.json["message"]


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publications_post_returns_document_metadata_error_for_malformed_json(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    async def fail_lookup(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Invalid requests must not query Elasticsearch")

    monkeypatch.setattr(DocumentMetadataService, "get_publications", fail_lookup)

    _, response = await test_annotator.asgi_client.post(
        "/publications",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json == {
        "endpoint": "/publications",
        "message": "The request body must contain valid JSON.",
    }


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", f"/publications?pubids={PMID}", None),
        ("get", f"/publications/{PMID}", None),
        ("post", "/publications", {"ids": [PMID]}),
    ],
)
async def test_publication_endpoints_return_sanitized_server_error(
    test_annotator: sanic.Sanic,
    monkeypatch,
    method,
    path,
    body,
):
    async def fail_lookup(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("sensitive Elasticsearch details")

    monkeypatch.setattr(DocumentMetadataService, "get_publications", fail_lookup)

    if method == "post":
        _, response = await test_annotator.asgi_client.post(path, json=body)
    else:
        _, response = await test_annotator.asgi_client.get(path)

    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json == {
        "endpoint": "/publications",
        "message": "Unable to retrieve document metadata.",
    }
    assert "sensitive" not in response.text
