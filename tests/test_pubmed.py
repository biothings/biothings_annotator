"""PubMed metadata routing tests."""

import os
from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest

from biothings_annotator.annotator import utils as annotator_utils
from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.exceptions import SourceDiscoveryError, UnsupportedSourceBackendError
from biothings_annotator.annotator.settings import (
    ANNOTATOR_CLIENTS,
    BIOLINK_PREFIX_to_BioThings,
)
from biothings_annotator.annotator.utils import parse_curie


PMID = "PMID:12345678"
LIVE_PMID = "PMID:31763219"
INVALID_PMID = "PMID:3176321900"
PUBMED_CURIES = [PMID, "doi:10.1242/jcs.03153", "DOI:10.1242/JCS.03153", "PMC:PMC1904490", "pmc:PMC1904490"]
PUBMED_METADATA = {
    "journal": {"name": "Example Journal", "abbr": "Example J"},
    "title": "Example title",
    "vol": "1",
    "iss": "2",
    "pub_date": "2026-06-30",
    "abstract": "Example abstract",
}
SKIPPED_PUBMED_RESULT = [
    {
        "query": PMID,
        "notfound": True,
        "skipped": True,
        "reason": "source_unavailable_for_backend",
        "source": "pubmed",
        "query_backend": "biothings",
    }
]


class FakePubMedClient:
    def __init__(self, notfound=False):
        self.notfound = notfound
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
        if self.notfound:
            return [{"query": query, "notfound": True} for query in query_list]
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
    }
    assert parse_curie(PMID) == ("pubmed", PMID)
    pubmed_settings = ANNOTATOR_CLIENTS["pubmed"]
    assert pubmed_settings["query_backends"] == ["elasticsearch"]
    assert "client" not in pubmed_settings
    assert pubmed_settings["elasticsearch"]["index"] == "annotator-pubmed"
    assert pubmed_settings["fields"] == [
        "pubmed.identifiers",
        "pubmed.journal.name",
        "pubmed.journal.abbr",
        "pubmed.title",
        "pubmed.vol",
        "pubmed.iss",
        "pubmed.pub_date",
        "pubmed.pubdate_raw",
        "pubmed.abstract",
    ]
    assert pubmed_settings["scopes"] == ["_id"]


@pytest.mark.unit
@pytest.mark.parametrize("prefix", ["doi", "DOI", "PMC", "pmc"])
def test_doi_and_pmc_route_to_pubmed_identifiers_scope(prefix):
    assert BIOLINK_PREFIX_to_BioThings[prefix] == {
        "type": "pubmed",
        "scopes": ["pubmed.identifiers"],
        "keep_prefix": True,
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "curie",
    ["doi:10.1242/jcs.03153", "DOI:10.1242/JCS.03153", "PMC:PMC1904490", "pmc:PMC1904490"],
)
def test_doi_and_pmc_curies_keep_the_full_curie_as_the_query_value(curie):
    """The identifiers array stores full CURIEs, so the prefix must survive parsing."""
    assert parse_curie(curie) == ("pubmed", curie)


@pytest.mark.unit
def test_pmid_keeps_the_id_scope_when_grouped_with_doi_and_pmc():
    """PMIDs must stay on the _id fast scope even when mixed with other prefixes."""
    annotator = Annotator(query_backend="elasticsearch")
    node_list = [PMID, "doi:10.1242/jcs.03153", "PMC:PMC1904490", "DOI:10.1000/xyz"]

    assert annotator._group_curies_by_scopes("pubmed", node_list) == [
        (["_id"], [PMID]),
        (["pubmed.identifiers"], ["doi:10.1242/jcs.03153", "PMC:PMC1904490", "DOI:10.1000/xyz"]),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_annotate_doi_queries_the_identifiers_field(monkeypatch):
    client = FakePubMedClient()
    doi = "doi:10.1242/jcs.03153"

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )

    result = await Annotator(query_backend="elasticsearch").annotate_curie(doi)

    assert result[doi][0]["query"] == doi
    assert client.querymany_calls == [
        {
            "query_list": [doi],
            "scopes": ["pubmed.identifiers"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_annotate_pmid_routes_to_elasticsearch_client(monkeypatch):
    client = FakePubMedClient()

    async def fail_source_discovery(*args, **kwargs):
        raise AssertionError("Elasticsearch must not perform BioThings source discovery")

    def get_fake_client(node_type, query_backend, api_host, elasticsearch_connection):
        del api_host, elasticsearch_connection
        assert node_type == "pubmed"
        assert query_backend == "elasticsearch"
        return client

    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_query_client", get_fake_client)
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        fail_source_discovery,
    )

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


@pytest.fixture
def biothings_pubmed_upstream(monkeypatch):
    """An upstream listing cannot change the annotator's static PubMed support."""
    def configure(state):
        discovery = AsyncMock(return_value=frozenset({"pubmed"}) if state == "available" else frozenset())
        if state == "failed":
            discovery.side_effect = SourceDiscoveryError()
        client_factory = Mock(side_effect=AssertionError("PubMed must not construct a BioThings client"))
        query_factory = Mock(side_effect=AssertionError("PubMed must not query the BioThings backend"))
        monkeypatch.setattr("biothings_annotator.annotator.annotator.get_biothings_sources", discovery)
        monkeypatch.setattr(annotator_utils, "get_biothings_sources", discovery)
        monkeypatch.setattr("biothings_annotator.annotator.annotator.get_client", client_factory)
        monkeypatch.setattr("biothings_annotator.annotator.annotator.get_query_client", query_factory)
        return discovery, client_factory, query_factory

    return configure


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_bulk_skip_matches_elasticsearch_notfound_result_shape(monkeypatch):
    client = FakePubMedClient(notfound=True)
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )

    elasticsearch_result = await Annotator(query_backend="elasticsearch").annotate_curie(INVALID_PMID)
    biothings_result = await Annotator(query_backend="biothings").annotate_curie_list([INVALID_PMID])

    elasticsearch_hit = elasticsearch_result[INVALID_PMID][0]
    skipped_hit = biothings_result[INVALID_PMID][0]
    assert elasticsearch_hit == {"query": INVALID_PMID, "notfound": True}
    assert {key: skipped_hit[key] for key in elasticsearch_hit} == elasticsearch_hit
    assert skipped_hit == {**SKIPPED_PUBMED_RESULT[0], "query": INVALID_PMID}
    assert len(client.querymany_calls) == 1
    assert client.querymany_calls[0]["query_list"] == [INVALID_PMID]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("curie", PUBMED_CURIES)
@pytest.mark.parametrize("upstream_state", ["available", "absent", "failed"])
async def test_single_biothings_pubmed_is_rejected_without_contacting_upstream(
    biothings_pubmed_upstream, curie, upstream_state
):
    upstream_calls = biothings_pubmed_upstream(upstream_state)
    annotator = Annotator(query_backend="biothings")

    with pytest.raises(UnsupportedSourceBackendError) as exc_info:
        await annotator.annotate_curie(curie)

    assert exc_info.value.source == "pubmed"
    assert exc_info.value.query_backend == "biothings"
    assert exc_info.value.supported_backends == ["elasticsearch"]
    assert exc_info.value.message
    assert annotator.skipped_curie_prefixes == []
    for call in upstream_calls:
        call.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["bulk", "trapi"])
@pytest.mark.parametrize("upstream_state", ["available", "absent", "failed"])
async def test_biothings_mixed_requests_skip_all_pubmed_prefixes_and_keep_gene_annotations(
    monkeypatch, biothings_pubmed_upstream, route, upstream_state
):
    discovery, client_factory, _ = biothings_pubmed_upstream(upstream_state)
    gene_curie = "NCBIGene:1017"
    gene_annotation = {"query": "1017", "_id": "1017", "symbol": "CDK2"}
    gene_client = Mock()
    gene_client.querymany = AsyncMock(return_value=[gene_annotation])

    def get_gene_client(node_type, query_backend, api_host, elasticsearch_connection):
        assert node_type == "gene"
        assert query_backend == "biothings"
        return gene_client

    query_factory = Mock(side_effect=get_gene_client)
    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_query_client", query_factory)
    annotator = Annotator(query_backend="biothings")
    curies = [PUBMED_CURIES[0], gene_curie, *PUBMED_CURIES[1:]]
    skipped = {curie: [{**SKIPPED_PUBMED_RESULT[0], "query": curie}] for curie in PUBMED_CURIES}
    expected = {**skipped, gene_curie: [gene_annotation]}

    if route == "bulk":
        result = await annotator.annotate_curie_list(curies)
        assert result == expected
    else:
        result = await annotator.annotate_trapi(
            {"message": {"knowledge_graph": {"nodes": {curie: {} for curie in curies}}}}
        )
        assert result == {
            curie: {
                "attributes": [
                    {
                        "attribute_type_id": (
                            "biothings_annotations" if curie == gene_curie else "biothings_query_status"
                        ),
                        "value": expected[curie],
                    }
                ]
            }
            for curie in curies
        }
    assert annotator.skipped_curie_prefixes == [curie.split(":", 1)[0] for curie in PUBMED_CURIES]
    discovery.assert_not_called()
    client_factory.assert_not_called()
    query_factory.assert_called_once()
    gene_client.querymany.assert_awaited_once_with(
        ["1017"], scopes=["entrezgene", "retired"], fields=ANNOTATOR_CLIENTS["gene"]["fields"]
    )

    assert await annotator.annotate_curie_list(["UNKNOWN:1"]) == {"UNKNOWN:1": {}}
    assert annotator.skipped_curie_prefixes == []


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["query_annotations", "query_biothings"])
@pytest.mark.parametrize("upstream_state", ["available", "failed"])
async def test_direct_pubmed_biothings_queries_are_rejected_before_discovery_or_clients(
    biothings_pubmed_upstream, method, upstream_state
):
    upstream_calls = biothings_pubmed_upstream(upstream_state)
    annotator = Annotator(query_backend="biothings")

    with pytest.raises(UnsupportedSourceBackendError) as exc_info:
        await getattr(annotator, method)(node_type="pubmed", query_list=[PMID])

    assert exc_info.value.source == "pubmed"
    assert exc_info.value.query_backend == "biothings"
    assert exc_info.value.supported_backends == ["elasticsearch"]
    for call in upstream_calls:
        call.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_biothings_query_cannot_bypass_pubmed_restriction_on_an_es_instance(biothings_pubmed_upstream):
    upstream_calls = biothings_pubmed_upstream("available")

    with pytest.raises(UnsupportedSourceBackendError) as exc_info:
        await Annotator(query_backend="elasticsearch").query_biothings("pubmed", [PMID])

    assert exc_info.value.query_backend == "biothings"
    for call in upstream_calls:
        call.assert_not_called()


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
        "ci_forward",
    )

    result = await annotator.annotate_curie(LIVE_PMID, include_extra=False)

    assert len(result[LIVE_PMID]) == 1
    hit = result[LIVE_PMID][0]
    assert hit["query"] == LIVE_PMID
    assert hit["_id"] == LIVE_PMID
    assert hit["pubmed"]["title"]
    assert hit["pubmed"]["journal"]["name"]
    assert hit["pubmed"]["pub_date"]
