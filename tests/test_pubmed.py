"""PubMed metadata routing tests."""

import os
from copy import deepcopy

import pytest

from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.settings import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings
from biothings_annotator.annotator.utils import parse_curie


PMID = "PMID:12345678"
LIVE_PMID = "PMID:31763219"
PUBMED_METADATA = {
    "journal": {"name": "Example Journal", "abbr": "Example J"},
    "title": "Example title",
    "vol": "1",
    "iss": "2",
    "pub_date": "2026-06-30",
    "abstract": "Example abstract",
}
SKIPPED_PUBMED_RESULT = {
    "query": PMID,
    "skipped": True,
    "reason": "source_unavailable_for_backend",
    "source": "pubmed",
    "query_backend": "biothings",
}


class FakePubMedClient:
    def __init__(self):
        self.querymany_calls = []

    async def querymany(self, query_list, scopes, fields):
        query_list = list(query_list)
        self.querymany_calls.append(
            {
                "query_list": query_list,
                "scopes": deepcopy(scopes),
                "fields": deepcopy(fields),
            }
        )
        return [
            {
                "query": query,
                "_id": query,
                "pubmed": deepcopy(PUBMED_METADATA),
            }
            for query in query_list
        ]


@pytest.mark.unit
def test_pmid_routes_to_standalone_pubmed_alias_without_stripping_prefix():
    assert BIOLINK_PREFIX_to_BioThings["PMID"] == {
        "type": "pubmed",
        "scopes": ["_id"],
        "keep_prefix": True,
        "query_backends": ("elasticsearch",),
    }
    assert parse_curie(PMID) == ("pubmed", PMID)
    assert ANNOTATOR_CLIENTS["pubmed"] == {
        "client": {"configuration": None, "endpoint": None, "instance": None},
        "elasticsearch": {"index": "annotator-pubmed", "instance": None},
        "fields": [
            "pubmed.journal.name",
            "pubmed.journal.abbr",
            "pubmed.title",
            "pubmed.vol",
            "pubmed.iss",
            "pubmed.pub_date",
            "pubmed.abstract",
        ],
        "scopes": ["_id"],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_annotate_pmid_routes_to_elasticsearch_client(monkeypatch):
    client = FakePubMedClient()

    def get_fake_client(node_type, query_backend, api_host, elasticsearch_connection):
        del api_host, elasticsearch_connection
        assert node_type == "pubmed"
        assert query_backend == "elasticsearch"
        return client

    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_query_client", get_fake_client)

    result = await Annotator(query_backend="elasticsearch").annotate_curie(PMID)

    assert result == {
        PMID: [
            {
                "query": PMID,
                "_id": PMID,
                "pubmed": PUBMED_METADATA,
            }
        ]
    }
    assert client.querymany_calls == [
        {
            "query_list": [PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_backend_skips_pmid_without_querying_a_client(monkeypatch):
    def fail_get_query_client(*args, **kwargs):
        raise AssertionError("BioThings backend must not attempt a PMID query")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        fail_get_query_client,
    )
    annotator = Annotator(query_backend="biothings")

    assert await annotator.annotate_curie(PMID) == {PMID: SKIPPED_PUBMED_RESULT}
    assert annotator.skipped_curie_prefixes == ["PMID"]
    assert await annotator.annotate_curie_list([PMID]) == {PMID: SKIPPED_PUBMED_RESULT}
    assert annotator.skipped_curie_prefixes == ["PMID"]
    assert await annotator.annotate_trapi(
        {
            "message": {
                "knowledge_graph": {
                    "nodes": {
                        PMID: {},
                    }
                }
            }
        }
    ) == {
        PMID: {
            "attributes": [
                {
                    "attribute_type_id": "biothings_query_status",
                    "value": SKIPPED_PUBMED_RESULT,
                }
            ]
        }
    }
    assert annotator.skipped_curie_prefixes == ["PMID"]

    assert await annotator.annotate_curie_list(["UNKNOWN:1"]) == {"UNKNOWN:1": {}}
    assert annotator.skipped_curie_prefixes == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_elasticsearch_pmid_batch_and_trapi_annotations_preserve_full_curie(monkeypatch):
    client = FakePubMedClient()

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )
    annotator = Annotator(query_backend="elasticsearch")

    batch_result = await annotator.annotate_curie_list([PMID])
    trapi_result = await annotator.annotate_trapi(
        {
            "message": {
                "knowledge_graph": {
                    "nodes": {
                        PMID: {},
                    }
                }
            }
        }
    )

    expected_annotation = {
        "query": PMID,
        "_id": PMID,
        "pubmed": PUBMED_METADATA,
    }
    assert batch_result == {PMID: [expected_annotation]}
    assert trapi_result == {
        PMID: {
            "attributes": [
                {
                    "attribute_type_id": "biothings_annotations",
                    "value": [expected_annotation],
                }
            ]
        }
    }
    assert client.querymany_calls == [
        {
            "query_list": [PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        },
        {
            "query_list": [PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        },
    ]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
async def test_live_ci_elasticsearch_returns_pubmed_metadata():
    annotator = Annotator(query_backend="elasticsearch")
    annotator.elasticsearch_connection = os.environ.get(
        "PUBMED_INTEGRATION_ELASTICSEARCH_CONNECTION",
        "ci_local_forward",
    )

    result = await annotator.annotate_curie(LIVE_PMID, include_extra=False)

    assert len(result[LIVE_PMID]) == 1
    hit = result[LIVE_PMID][0]
    assert hit["query"] == LIVE_PMID
    assert hit["_id"] == LIVE_PMID
    assert hit["pubmed"]["title"]
    assert hit["pubmed"]["journal"]["name"]
    assert hit["pubmed"]["pub_date"]
