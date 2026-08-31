"""PubMed metadata routing tests."""

import os
from copy import deepcopy

import pytest

from biothings_annotator.annotator import utils as annotator_utils
from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.exceptions import SourceDiscoveryError
from biothings_annotator.annotator.settings import (
    ANNOTATOR_CLIENTS,
    BIOLINK_PREFIX_to_BioThings,
    SERVICE_PROVIDER_API_HOST,
)
from biothings_annotator.annotator.utils import parse_curie


PMID = "PMID:12345678"
LIVE_PMID = "PMID:31763219"
INVALID_PMID = "PMID:3176321900"
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
    assert {
        key: pubmed_settings["client"].get(key)
        for key in ("configuration", "endpoint", "source")
    } == {
        "configuration": None,
        "endpoint": "pubmed",
        "source": "pubmed",
    }
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_skip_matches_elasticsearch_notfound_result_shape(monkeypatch):
    client = FakePubMedClient(notfound=True)

    async def sources_without_pubmed(api_host):
        del api_host
        return frozenset()

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_without_pubmed,
    )

    elasticsearch_result = await Annotator(query_backend="elasticsearch").annotate_curie(INVALID_PMID)
    biothings_result = await Annotator(query_backend="biothings").annotate_curie(INVALID_PMID)

    assert elasticsearch_result == {
        INVALID_PMID: [
            {
                "query": INVALID_PMID,
                "notfound": True,
            }
        ]
    }
    assert isinstance(biothings_result[INVALID_PMID], list)
    assert len(biothings_result[INVALID_PMID]) == 1
    elasticsearch_hit = elasticsearch_result[INVALID_PMID][0]
    skipped_hit = biothings_result[INVALID_PMID][0]
    assert {key: skipped_hit[key] for key in elasticsearch_hit} == elasticsearch_hit
    assert skipped_hit == {
        "query": INVALID_PMID,
        "notfound": True,
        "skipped": True,
        "reason": "source_unavailable_for_backend",
        "source": "pubmed",
        "query_backend": "biothings",
    }
    assert client.querymany_calls == [
        {
            "query_list": [INVALID_PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_backend_skips_pmid_without_querying_a_client(monkeypatch):
    async def sources_without_pubmed(api_host):
        del api_host
        return frozenset()

    def fail_get_query_client(*args, **kwargs):
        raise AssertionError("BioThings backend must not attempt a PMID query")

    def fail_get_client(*args, **kwargs):
        raise AssertionError("Absent BioThings source must not construct a PMID client")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_without_pubmed,
    )
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        fail_get_query_client,
    )
    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_client", fail_get_client)
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
async def test_biothings_backend_queries_pmid_when_source_becomes_available(monkeypatch):
    client = FakePubMedClient()
    discovery_calls = []

    async def sources_with_pubmed(api_host):
        discovery_calls.append(api_host)
        return frozenset({"pubmed"})

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_with_pubmed,
    )
    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_client", lambda node_type, api_host: client)
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )
    annotator = Annotator(query_backend="biothings")

    result = await annotator.annotate_curie_list([PMID, LIVE_PMID])
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

    expected_hits = {
        query: [
            {
                "query": query,
                "_id": query,
                "pubmed": PUBMED_METADATA,
            }
        ]
        for query in (PMID, LIVE_PMID)
    }
    assert result == expected_hits
    assert trapi_result == {
        PMID: {
            "attributes": [
                {
                    "attribute_type_id": "biothings_annotations",
                    "value": expected_hits[PMID],
                }
            ]
        }
    }
    assert annotator.skipped_curie_prefixes == []
    assert discovery_calls == [annotator.api_host, annotator.api_host]
    assert client.querymany_calls == [
        {
            "query_list": [PMID, LIVE_PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        },
        {
            "query_list": [PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_pubmed_auto_activates_after_source_cache_refresh(monkeypatch):
    client = FakePubMedClient()
    clock = {"now": 100.0}
    source_lists = [frozenset(), frozenset({"pubmed"})]
    discovery_calls = []

    async def fake_fetch_sources(api_host):
        discovery_calls.append(api_host)
        return source_lists.pop(0)

    monkeypatch.setattr(annotator_utils, "fetch_biothings_sources", fake_fetch_sources)
    monkeypatch.setattr(annotator_utils.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_client", lambda node_type, api_host: client)
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )

    annotator_utils.clear_biothings_source_cache()
    try:
        initial_result = await Annotator(query_backend="biothings").annotate_curie(PMID)
        clock["now"] += annotator_utils.BIOTHINGS_SOURCE_DISCOVERY_TTL - 1
        cached_result = await Annotator(query_backend="biothings").annotate_curie(PMID)
        clock["now"] += 2
        activated_result = await Annotator(query_backend="biothings").annotate_curie(PMID)
    finally:
        annotator_utils.clear_biothings_source_cache()

    expected_annotation = [
        {
            "query": PMID,
            "_id": PMID,
            "pubmed": PUBMED_METADATA,
        }
    ]
    assert initial_result == {PMID: SKIPPED_PUBMED_RESULT}
    assert cached_result == {PMID: SKIPPED_PUBMED_RESULT}
    assert activated_result == {PMID: expected_annotation}
    assert discovery_calls == [
        SERVICE_PROVIDER_API_HOST,
        SERVICE_PROVIDER_API_HOST,
    ]
    assert client.querymany_calls == [
        {
            "query_list": [PMID],
            "scopes": ["_id"],
            "fields": ANNOTATOR_CLIENTS["pubmed"]["fields"],
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_available_biothings_pubmed_returns_normal_notfound_result(monkeypatch):
    client = FakePubMedClient(notfound=True)

    async def sources_with_pubmed(api_host):
        del api_host
        return frozenset({"pubmed"})

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_with_pubmed,
    )
    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_client", lambda node_type, api_host: client)
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        lambda node_type, query_backend, api_host, elasticsearch_connection: client,
    )
    annotator = Annotator(query_backend="biothings")

    result = await annotator.annotate_curie(INVALID_PMID)

    assert result == {INVALID_PMID: [{"query": INVALID_PMID, "notfound": True}]}
    assert annotator.skipped_curie_prefixes == []


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("client_failure", ["returns_none", "raises"])
async def test_listed_biothings_pubmed_with_unusable_client_is_not_reported_as_skipped(
    monkeypatch,
    client_failure,
):
    async def sources_with_pubmed(api_host):
        del api_host
        return frozenset({"pubmed"})

    def fail_client_construction(node_type, api_host):
        del node_type, api_host
        if client_failure == "raises":
            raise RuntimeError("client construction failed")
        return None

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_with_pubmed,
    )
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_client",
        fail_client_construction,
    )
    annotator = Annotator(query_backend="biothings")

    with pytest.raises(SourceDiscoveryError) as exc_info:
        await annotator.annotate_curie(PMID)

    assert exc_info.value.source == "pubmed"
    assert annotator.skipped_curie_prefixes == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_pubmed_discovery_failure_is_not_reported_as_skipped(monkeypatch):
    async def fail_source_discovery(api_host):
        del api_host
        raise SourceDiscoveryError()

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        fail_source_discovery,
    )
    annotator = Annotator(query_backend="biothings")

    with pytest.raises(SourceDiscoveryError) as exc_info:
        await annotator.annotate_curie(PMID)

    assert exc_info.value.source == "pubmed"
    assert annotator.skipped_curie_prefixes == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_biothings_query_skips_pubmed_only_while_source_is_absent(monkeypatch):
    async def sources_without_pubmed(api_host):
        assert api_host == SERVICE_PROVIDER_API_HOST
        return frozenset({"gene", "chem", "disease", "phenotype"})

    def fail_client_construction(*args, **kwargs):
        del args, kwargs
        raise AssertionError("An absent BioThings source must not be queried")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_without_pubmed,
    )
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_client",
        fail_client_construction,
    )

    result = await Annotator(query_backend="biothings").query_biothings(
        node_type="pubmed",
        query_list=[PMID],
    )

    assert result == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_biothings_query_does_not_treat_discovery_failure_as_absence(monkeypatch):
    async def fail_source_discovery(api_host):
        del api_host
        raise SourceDiscoveryError()

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        fail_source_discovery,
    )

    with pytest.raises(SourceDiscoveryError) as exc_info:
        await Annotator(query_backend="biothings").query_biothings(
            node_type="pubmed",
            query_list=[PMID],
        )

    assert exc_info.value.source == "pubmed"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("client_failure", ["returns_none", "raises"])
async def test_direct_biothings_query_does_not_skip_present_source_with_unusable_client(
    monkeypatch,
    client_failure,
):
    async def sources_with_pubmed(api_host):
        del api_host
        return frozenset({"pubmed"})

    def fail_client_construction(node_type, api_host):
        del node_type, api_host
        if client_failure == "raises":
            raise RuntimeError("client construction failed")
        return None

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_biothings_sources",
        sources_with_pubmed,
    )
    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_client",
        fail_client_construction,
    )

    with pytest.raises(SourceDiscoveryError) as exc_info:
        await Annotator(query_backend="biothings").query_biothings(
            node_type="pubmed",
            query_list=[PMID],
        )

    assert exc_info.value.source == "pubmed"


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
