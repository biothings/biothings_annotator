"""Tests for the dedicated PubMed document metadata fast path."""

import asyncio
import os
import re

import pytest
import sanic

from biothings_annotator.annotator.document_metadata import (
    DocumentMetadataService,
    format_publication_metadata,
)
from biothings_annotator.annotator.settings import ANNOTATOR_CLIENTS
from biothings_annotator.annotator.utils import get_elasticsearch_client
from biothings_annotator.application.views.document_metadata import (
    BULK_SEARCH_LOOKUP_STRATEGY,
    COMBINED_SEARCH_LOOKUP_STRATEGY,
    CURRENT_LOOKUP_STRATEGY,
    PUBLICATIONS_LOOKUP_STRATEGY_HEADER,
    SUPPORTED_PUBLICATION_ID_MESSAGE,
    validate_publication_ids,
)

PMID = "PMID:30690000"
MISSING_PMID = "PMID:82374"
DOI = "doi:10.1242/jcs.03153"
MISSING_DOI = "doi:10.1000/absent"
PMCID = "PMC:PMC1904490"
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
def test_document_metadata_service_uses_default_in_cluster_connection(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_CONNECTION", raising=False)

    service = DocumentMetadataService()

    assert service.elasticsearch_connection == "in_cluster"


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
@pytest.mark.parametrize(
    "pubdate_raw, expected",
    [
        # The first two are CCWG#15's own response-spec examples.
        ("2019 Mar 15", ("2019", "Mar", "15")),
        ("1994 Sep-Dec", ("1994", "Sep-Dec", "")),
        ("1998 Dec-1999 Jan", ("1998", "Dec-1999 Jan", "")),
        ("2019", ("2019", "", "")),
        ("2019 Winter", ("2019", "Winter", "")),
        ("2019 Mar 05", ("2019", "Mar", "5")),
        # A trailing number outside the day range stays part of the month rather
        # than being projected as a nonsense day.
        ("2019 Mar 44", ("2019", "Mar 44", "")),
        ("", ("", "", "")),
        ("n.d.", ("", "", "")),
        (None, ("", "", "")),
    ],
)
def test_format_publication_metadata_projects_verbatim_pubdate_ranges(pubdate_raw, expected):
    metadata = {"pubdate_raw": pubdate_raw} if pubdate_raw is not None else {}
    formatted = format_publication_metadata(metadata)

    assert (formatted["pub_year"], formatted["pub_month"], formatted["pub_day"]) == expected


@pytest.mark.unit
def test_format_publication_metadata_prefers_pubdate_raw_over_iso_pub_date():
    formatted = format_publication_metadata({"pubdate_raw": "1994 Sep-Dec", "pub_date": "1994-09-01"})

    assert (formatted["pub_year"], formatted["pub_month"], formatted["pub_day"]) == ("1994", "Sep-Dec", "")


@pytest.mark.unit
@pytest.mark.parametrize("pubdate_raw", ["", "n.d.", None])
def test_format_publication_metadata_falls_back_to_iso_pub_date(pubdate_raw):
    """Absent pubdate_raw is the current index's shape, so the ISO path must still serve it."""
    metadata = {"pub_date": "2019-03-15"}
    if pubdate_raw is not None:
        metadata["pubdate_raw"] = pubdate_raw
    formatted = format_publication_metadata(metadata)

    assert (formatted["pub_year"], formatted["pub_month"], formatted["pub_day"]) == ("2019", "Mar", "15")


@pytest.mark.unit
@pytest.mark.parametrize(
    "pub_date, expected",
    [
        ("1994 Sep-Dec", ("1994", "Sep-Dec", "")),
        ("1998 Dec-1999 Jan", ("1998", "Dec-1999 Jan", "")),
        ("2019 Mar 15", ("2019", "Mar", "15")),
        # A bare year range shares its leading shape with an ISO date. Reading it
        # as ISO yields ("1987", "", "") and drops the closing year outright.
        ("1987-1988", ("1987-1988", "", "")),
        ("1998-1999", ("1998-1999", "", "")),
        # Still parsed as ISO when that is the shape it arrives in, including the
        # two-digit tail that cannot be distinguished from a month.
        ("2019-03-15", ("2019", "Mar", "15")),
        ("2026-07", ("2026", "Jul", "")),
        ("1987-88", ("1987", "", "")),
    ],
)
def test_format_publication_metadata_reads_a_verbatim_date_from_pub_date(pub_date, expected):
    """Which field carries the verbatim value depends on the exporter revision.

    The ISO parser returns empty strings for a range, so a verbatim value landing
    in pub_date rather than pubdate_raw would silently lose the whole date.
    """
    formatted = format_publication_metadata({"pub_date": pub_date})

    assert (formatted["pub_year"], formatted["pub_month"], formatted["pub_day"]) == expected


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

    service = DocumentMetadataService(elasticsearch_connection="in_cluster")
    results, not_found = await service.get_publications([PMID, MISSING_PMID])

    assert calls == [
        {"node_type": "pubmed", "elasticsearch_connection": "in_cluster"},
        {"query_list": [PMID, MISSING_PMID], "fields": ["pubmed"]},
    ]
    assert results == {PMID: FORMATTED_METADATA}
    assert not_found == [MISSING_PMID]


@pytest.mark.unit
@pytest.mark.parametrize(
    "publication_id",
    [
        "PMID:30690000",
        "PMC:PMC1904490",
        "pmc:PMC1904490",
        "doi:10.1242/jcs.03153",
        "DOI:10.1242/JCS.03153",
        "doi:10.1000/xyz(123)/abc",
    ],
)
def test_validate_publication_ids_accepts_pmid_pmc_and_doi(publication_id):
    assert validate_publication_ids([publication_id]) == [publication_id]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_document_metadata_service_splits_exact_ids_from_scoped_lookups(monkeypatch):
    """PMIDs keep the one-request mget path; only DOI and PMCID pay for the msearch."""
    calls = []

    class FakePubMedClient:
        async def mget(self, query_list, fields):
            calls.append({"method": "mget", "query_list": query_list, "fields": fields})
            return [{"query": PMID, "_id": PMID, "pubmed": PUBMED_METADATA}]

        async def querymany_exact(self, query_list, field, fields, size):
            calls.append(
                {
                    "method": "querymany_exact",
                    "query_list": query_list,
                    "field": field,
                    "fields": fields,
                    "size": size,
                }
            )
            # The document is stored under its PMID _id, so the submitted DOI is
            # only recoverable from the echoed query field.
            return [
                {"query": DOI, "_id": PMID, "pubmed": PUBMED_METADATA},
                {"query": MISSING_DOI, "notfound": True},
            ]

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: FakePubMedClient(),
    )

    service = DocumentMetadataService(elasticsearch_connection="in_cluster")
    results, not_found = await service.get_publications([DOI, PMID, MISSING_DOI])

    assert calls == [
        {"method": "mget", "query_list": [PMID], "fields": ["pubmed"]},
        {
            "method": "querymany_exact",
            "query_list": [DOI, MISSING_DOI],
            "field": "pubmed.identifiers",
            "fields": ["pubmed"],
            "size": 1,
        },
    ]
    # Keyed by the submitted identifier and ordered by the request, not by the
    # backend call that resolved each one.
    assert list(results) == [DOI, PMID]
    assert results[DOI] == FORMATTED_METADATA
    assert not_found == [MISSING_DOI]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_document_metadata_service_skips_the_scoped_lookup_for_pmid_only_requests(monkeypatch):
    calls = []

    class FakePubMedClient:
        async def mget(self, query_list, fields):
            del fields
            calls.append("mget")
            return [{"query": query_id, "_id": query_id, "pubmed": PUBMED_METADATA} for query_id in query_list]

        async def querymany(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("A PMID-only request must not issue a scoped lookup")

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: FakePubMedClient(),
    )

    service = DocumentMetadataService(elasticsearch_connection="in_cluster")
    results, not_found = await service.get_publications([f"PMID:{index}" for index in range(1, 101)])

    assert calls == ["mget"]
    assert len(results) == 100
    assert not_found == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_document_metadata_service_canonicalizes_the_pmid_prefix_for_exact_id_lookup(monkeypatch):
    """A loosely cased PMID must still hit the document stored under PMID:<digits>."""
    requested = []

    class FakePubMedClient:
        async def mget(self, query_list, fields):
            del fields
            requested.append(list(query_list))
            # Elasticsearch matches _id byte-exactly; only the stored casing resolves.
            return [
                (
                    {"query": query_id, "_id": query_id, "pubmed": PUBMED_METADATA}
                    if query_id == PMID
                    else {"query": query_id, "notfound": True}
                )
                for query_id in query_list
            ]

        async def querymany(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("A PMID-only request must not issue a scoped lookup")

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: FakePubMedClient(),
    )

    service = DocumentMetadataService(elasticsearch_connection="in_cluster")
    submitted = [PMID, PMID.lower(), "Pmid:30690000"]
    results, not_found = await service.get_publications(submitted)

    # Three spellings collapse to one backend lookup, and each is still keyed as sent.
    assert requested == [[PMID]]
    assert list(results) == submitted
    assert not_found == []
    assert all(result == FORMATTED_METADATA for result in results.values())


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capability_fields, expected",
    [
        (
            ["pubmed.identifiers", "pubmed.pubdate_raw"],
            {"multi_identifier_lookup": True, "verbatim_publication_date": True, "missing_required_fields": []},
        ),
        (
            ["pubmed.identifiers"],
            {"multi_identifier_lookup": True, "verbatim_publication_date": False, "missing_required_fields": []},
        ),
        # The shape of the index before the identifiers reindex: DOI and PMCID
        # lookups silently return nothing, which is what makes the probe necessary.
        (
            ["pubmed.pubdate_raw"],
            {
                "multi_identifier_lookup": False,
                "verbatim_publication_date": True,
                "missing_required_fields": ["pubmed.identifiers"],
            },
        ),
        (
            [],
            {
                "multi_identifier_lookup": False,
                "verbatim_publication_date": False,
                "missing_required_fields": ["pubmed.identifiers"],
            },
        ),
    ],
)
async def test_check_index_fields_reports_multi_identifier_capability(monkeypatch, capability_fields, expected):
    class FakePubMedClient:
        index = "annotator-pubmed"

        async def field_capabilities(self, fields):
            # Elasticsearch omits absent fields from the field-caps response and
            # always reports "searchable" for the ones it does return.
            return {
                field: {"keyword": {"type": "keyword", "searchable": True}}
                for field in fields
                if field in capability_fields
            }

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: FakePubMedClient(),
    )

    report = await DocumentMetadataService(elasticsearch_connection="in_cluster").check_index_fields()

    assert report["index"] == "annotator-pubmed"
    assert report["multi_identifier_lookup"] is expected["multi_identifier_lookup"]
    assert report["verbatim_publication_date"] is expected["verbatim_publication_date"]
    assert report["missing_required_fields"] == expected["missing_required_fields"]
    assert report["fields"] == {
        "pubmed.identifiers": "pubmed.identifiers" in capability_fields,
        "pubmed.pubdate_raw": "pubmed.pubdate_raw" in capability_fields,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_index_fields_treats_an_unsearchable_identifier_field_as_unusable(monkeypatch):
    """A field mapped with index: false is present but matches nothing when queried."""

    class FakePubMedClient:
        index = "annotator-pubmed"

        async def field_capabilities(self, fields):
            del fields
            return {
                "pubmed.identifiers": {"keyword": {"type": "keyword", "searchable": False}},
                "pubmed.pubdate_raw": {"keyword": {"type": "keyword", "searchable": True}},
            }

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: FakePubMedClient(),
    )

    report = await DocumentMetadataService(elasticsearch_connection="in_cluster").check_index_fields()

    # Present in the mapping, but still reported as missing for lookup purposes.
    assert report["fields"]["pubmed.identifiers"] is True
    assert report["missing_required_fields"] == ["pubmed.identifiers"]
    assert report["multi_identifier_lookup"] is False
    assert report["verbatim_publication_date"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_index_fields_does_not_raise_when_the_field_is_absent(monkeypatch):
    """The field is legitimately absent until the reindex, so this must report, not fail."""

    class FakePubMedClient:
        index = "annotator-pubmed"

        async def field_capabilities(self, fields):
            del fields
            return {}

    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: FakePubMedClient(),
    )

    report = await DocumentMetadataService(elasticsearch_connection="in_cluster").check_index_fields()

    assert report["multi_identifier_lookup"] is False


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

    service = DocumentMetadataService(elasticsearch_connection="in_cluster", request_timeout=0.001)
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
        return {PMID: FORMATTED_METADATA}, [MISSING_PMID], False

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)

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
    assert response.json["_meta"]["lookup_strategy"] == CURRENT_LOOKUP_STRATEGY
    assert response.json["_meta"]["lookup_fallback"] is False
    assert response.headers["vary"] == PUBLICATIONS_LOOKUP_STRATEGY_HEADER
    assert isinstance(response.json["_meta"]["processing_time_ms"], int)
    assert response.json["_meta"]["processing_time_ms"] >= 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", response.json["_meta"]["timestamp"])


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publications_endpoint_selects_isolated_lookup_services_per_request(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    calls = []

    async def get_publications(self, publication_ids):
        calls.append((id(self), self.lookup_strategy, publication_ids))
        return {PMID: FORMATTED_METADATA}, [], False

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)

    _, default_response = await test_annotator.asgi_client.get(f"/publications?pubids={PMID}")
    _, bulk_search_response = await test_annotator.asgi_client.post(
        "/publications",
        json={"ids": [PMID]},
        headers={PUBLICATIONS_LOOKUP_STRATEGY_HEADER: BULK_SEARCH_LOOKUP_STRATEGY},
    )
    _, combined_search_response = await test_annotator.asgi_client.post(
        "/publications",
        json={"ids": [PMID]},
        headers={PUBLICATIONS_LOOKUP_STRATEGY_HEADER: COMBINED_SEARCH_LOOKUP_STRATEGY},
    )
    _, current_response = await test_annotator.asgi_client.get(
        f"/publications/{PMID}",
        headers={PUBLICATIONS_LOOKUP_STRATEGY_HEADER: CURRENT_LOOKUP_STRATEGY},
    )

    assert [call[1:] for call in calls] == [
        (CURRENT_LOOKUP_STRATEGY, [PMID]),
        (BULK_SEARCH_LOOKUP_STRATEGY, [PMID]),
        (COMBINED_SEARCH_LOOKUP_STRATEGY, [PMID]),
        (CURRENT_LOOKUP_STRATEGY, [PMID]),
    ]
    assert calls[0][0] == calls[3][0]
    assert calls[0][0] != calls[1][0]
    assert calls[0][0] != calls[2][0]
    assert calls[1][0] != calls[2][0]
    assert default_response.json["_meta"]["lookup_strategy"] == CURRENT_LOOKUP_STRATEGY
    assert bulk_search_response.json["_meta"]["lookup_strategy"] == BULK_SEARCH_LOOKUP_STRATEGY
    assert combined_search_response.json["_meta"]["lookup_strategy"] == COMBINED_SEARCH_LOOKUP_STRATEGY
    assert current_response.json["_meta"]["lookup_strategy"] == CURRENT_LOOKUP_STRATEGY
    assert default_response.json["_meta"]["lookup_fallback"] is False
    assert bulk_search_response.json["_meta"]["lookup_fallback"] is False
    assert combined_search_response.json["_meta"]["lookup_fallback"] is False
    assert current_response.json["_meta"]["lookup_fallback"] is False


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publications_endpoint_exposes_a_per_request_lookup_fallback_marker(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    calls = 0

    async def get_publications(self, publication_ids):
        nonlocal calls
        del self, publication_ids
        calls += 1
        return {PMID: FORMATTED_METADATA}, [], calls == 1

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)
    headers = {PUBLICATIONS_LOOKUP_STRATEGY_HEADER: BULK_SEARCH_LOOKUP_STRATEGY}

    _, fallback_response = await test_annotator.asgi_client.post("/publications", json={"ids": [PMID]}, headers=headers)
    _, normal_response = await test_annotator.asgi_client.post("/publications", json={"ids": [PMID]}, headers=headers)

    assert fallback_response.json["_meta"]["lookup_fallback"] is True
    assert normal_response.json["_meta"]["lookup_fallback"] is False


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
async def test_publication_endpoints_reject_an_invalid_lookup_strategy_before_lookup(
    test_annotator: sanic.Sanic,
    monkeypatch,
    method,
    path,
    body,
):
    async def fail_lookup(*args, **kwargs):
        del args, kwargs
        raise AssertionError("An invalid lookup strategy must not query Elasticsearch")

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", fail_lookup)
    headers = {PUBLICATIONS_LOOKUP_STRATEGY_HEADER: "experimental"}

    if method == "post":
        _, response = await test_annotator.asgi_client.post(path, json=body, headers=headers)
    else:
        _, response = await test_annotator.asgi_client.get(path, headers=headers)

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json == {
        "endpoint": "/publications",
        "message": (
            f"The {PUBLICATIONS_LOOKUP_STRATEGY_HEADER} header must be one of "
            f"{CURRENT_LOOKUP_STRATEGY}, {BULK_SEARCH_LOOKUP_STRATEGY}, or "
            f"{COMBINED_SEARCH_LOOKUP_STRATEGY}."
        ),
    }


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
        return {PMID: FORMATTED_METADATA}, [], False

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)

    _, response = await test_annotator.asgi_client.get(f"/publications/{PMID}?request_id=path-request")

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert calls == [[PMID]]
    assert response.json["results"] == {PMID: FORMATTED_METADATA}
    assert response.json["not_found"] == []
    assert response.json["_meta"]["n_results"] == 1
    assert response.json["_meta"]["request_id"] == "path-request"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("publication_id", [DOI, PMCID])
async def test_publication_path_endpoint_accepts_doi_and_pmcid(
    test_annotator: sanic.Sanic,
    monkeypatch,
    publication_id,
):
    """A DOI suffix contains slashes, so the path route must not truncate it."""
    calls = []

    async def get_publications(self, publication_ids):
        del self
        calls.append(publication_ids)
        return {publication_ids[0]: FORMATTED_METADATA}, [], False

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)

    _, response = await test_annotator.asgi_client.get(f"/publications/{publication_id}")

    assert response.status_code == 200
    assert calls == [[publication_id]]
    assert response.json["results"] == {publication_id: FORMATTED_METADATA}


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_publications_batch_forms_accept_mixed_prefixes(
    test_annotator: sanic.Sanic,
    monkeypatch,
):
    calls = []

    async def get_publications(self, publication_ids):
        del self
        calls.append(publication_ids)
        return {publication_ids[0]: FORMATTED_METADATA}, list(publication_ids[1:]), False

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)

    _, query_response = await test_annotator.asgi_client.get(f"/publications?pubids={PMID},{PMCID}")
    _, post_response = await test_annotator.asgi_client.post("/publications", json={"ids": [PMID, PMCID, DOI]})

    assert query_response.status_code == 200
    assert post_response.status_code == 200
    assert calls == [[PMID, PMCID], [PMID, PMCID, DOI]]


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
        return results, not_found, False

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", get_publications)

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
        ("?pubids=PMC:12345", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("?pubids=PMID:0", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("?pubids=PMID:not-a-number", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("?pubids=doi:notadoi", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("?pubids=CHEBI:15377", SUPPORTED_PUBLICATION_ID_MESSAGE),
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

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", fail_lookup)

    _, response = await test_annotator.asgi_client.get(f"/publications{query}")

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert message in response.json["message"]


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "publication_id, message",
    [
        ("PMC:12345", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("PMID:0", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("PMID:not-a-number", SUPPORTED_PUBLICATION_ID_MESSAGE),
        ("doi:notadoi", SUPPORTED_PUBLICATION_ID_MESSAGE),
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

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", fail_lookup)

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
        ({"ids": ["PMC:12345"]}, SUPPORTED_PUBLICATION_ID_MESSAGE),
        ({"ids": [PMID, 42]}, SUPPORTED_PUBLICATION_ID_MESSAGE),
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

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", fail_lookup)

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

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", fail_lookup)

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

    monkeypatch.setattr(DocumentMetadataService, "get_publications_with_metadata", fail_lookup)

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


LIVE_PMID = "PMID:16954148"
LIVE_ALTERNATE_IDENTIFIERS = ["PMC:PMC1904490", "doi:10.1242/jcs.03153"]
LIVE_PUBLICATION_IDENTIFIERS = [LIVE_PMID, *LIVE_ALTERNATE_IDENTIFIERS]
# Real values verified against NCBI upstream. The first two are CCWG#15's own
# response-spec examples.
LIVE_DATE_EXPECTATIONS = {
    "PMID:30690000": ("2019", "Mar", "15"),
    "PMID:8000234": ("1994", "Sep-Dec", ""),
    "PMID:10188493": ("1998", "Dec-1999 Jan", ""),
}
# pubmed2db PR #7's xrefs fix bounds a record at its own identifiers. A record
# carrying hundreds means the export regressed and is pulling in cited
# references' DOIs, which is a bad export rather than a code defect.
MAX_ALTERNATE_IDENTIFIERS_PER_RECORD = 2


@pytest.fixture
def live_pubmed_client():
    """Drop the cached client so each test builds one bound to its own event loop.

    get_elasticsearch_client memoizes the client on ANNOTATOR_CLIENTS, and the
    httpx client it owns is bound to whichever loop created it. That is correct
    for the server's single long-lived loop but not for a per-test loop.
    """
    ANNOTATOR_CLIENTS["pubmed"]["elasticsearch"]["instance"] = None
    yield
    ANNOTATOR_CLIENTS["pubmed"]["elasticsearch"]["instance"] = None


def _live_service(lookup_strategy: str = CURRENT_LOOKUP_STRATEGY) -> DocumentMetadataService:
    return DocumentMetadataService(
        elasticsearch_connection=os.environ.get(
            "PUBMED_INTEGRATION_ELASTICSEARCH_CONNECTION",
            "ci_forward",
        ),
        request_timeout=float(os.environ.get("PUBMED_INTEGRATION_REQUEST_TIMEOUT", "30")),
        lookup_strategy=lookup_strategy,
    )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
async def test_live_index_exposes_the_multi_identifier_field(live_pubmed_client):
    """Fail loudly when the alias cannot support DOI and PMCID lookup at all.

    A zero-hit DOI lookup looks identical to an absent paper, so this asserts the
    mapping directly rather than inferring capability from a query result.
    """
    report = await _live_service().check_index_fields()

    assert report["multi_identifier_lookup"], (
        f"{report['index']} is missing {report['missing_required_fields']}; "
        "DOI and PMCID lookups will report not_found for every identifier"
    )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
@pytest.mark.parametrize(
    "lookup_strategy",
    [CURRENT_LOOKUP_STRATEGY, BULK_SEARCH_LOOKUP_STRATEGY, COMBINED_SEARCH_LOOKUP_STRATEGY],
)
async def test_live_index_resolves_a_publication_by_every_identifier_type(live_pubmed_client, lookup_strategy):
    service = _live_service(lookup_strategy)

    results, not_found = await service.get_publications(LIVE_PUBLICATION_IDENTIFIERS)

    assert not_found == []
    # Every identifier must resolve to the same publication, keyed as submitted.
    titles = {results[identifier]["article_title"] for identifier in LIVE_PUBLICATION_IDENTIFIERS}
    assert len(titles) == 1
    assert titles.pop()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
@pytest.mark.parametrize(
    "lookup_strategy, identifier",
    [
        (strategy, identifier)
        for strategy in (CURRENT_LOOKUP_STRATEGY, BULK_SEARCH_LOOKUP_STRATEGY, COMBINED_SEARCH_LOOKUP_STRATEGY)
        for identifier in ("DOI:10.1242/JCS.03153", "doi:10.1242/JCS.03153", "pmc:PMC1904490")
    ],
)
async def test_live_index_matches_identifiers_case_insensitively(live_pubmed_client, lookup_strategy, identifier):
    results, not_found = await _live_service(lookup_strategy).get_publications([identifier])

    assert not_found == []
    assert results[identifier]["article_title"]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
async def test_live_combined_search_agrees_with_current_on_mixed_hits_and_misses(live_pubmed_client):
    publication_ids = [
        "pmid:16954148",
        "DOI:10.1242/JCS.03153",
        "pmc:PMC1904490",
        "PMID:999999999999",
        "doi:10.999999999999/not-a-real-publication",
    ]

    current_results, current_not_found = await _live_service(CURRENT_LOOKUP_STRATEGY).get_publications(publication_ids)
    # The fixture clears the cached client between tests, but both calls in this
    # test intentionally share the server-style client and event loop.
    combined_results, combined_not_found, lookup_fallback = await _live_service(
        COMBINED_SEARCH_LOOKUP_STRATEGY
    ).get_publications_with_metadata(publication_ids)

    assert combined_results == current_results
    assert list(combined_results) == publication_ids[:3]
    assert combined_not_found == current_not_found == publication_ids[3:]
    assert lookup_fallback is False


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
async def test_live_index_bounds_identifier_cardinality(live_pubmed_client):
    """A record with many identifiers means the export predates pubmed2db PR #7."""
    client = get_elasticsearch_client(
        "pubmed",
        os.environ.get("PUBMED_INTEGRATION_ELASTICSEARCH_CONNECTION", "ci_forward"),
    )

    hits = await client.mget([LIVE_PMID], fields=["pubmed.identifiers"])
    identifiers = hits[0]["pubmed"]["identifiers"]

    assert sorted(identifiers) == sorted(LIVE_ALTERNATE_IDENTIFIERS)
    assert LIVE_PMID not in identifiers
    assert len(identifiers) <= MAX_ALTERNATE_IDENTIFIERS_PER_RECORD


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_PUBMED_ES_INTEGRATION") != "1",
    reason="Set RUN_PUBMED_ES_INTEGRATION=1 to query the live PubMed Elasticsearch alias.",
)
async def test_live_index_projects_verbatim_publication_dates(live_pubmed_client):
    """Ranges must survive projection, which only pubdate_raw can express."""
    service = _live_service()
    report = await service.check_index_fields()
    if not report["verbatim_publication_date"]:
        pytest.skip("The export does not carry pubmed.pubdate_raw yet (pubmed2db PR #17).")

    results, not_found = await service.get_publications(list(LIVE_DATE_EXPECTATIONS))

    assert not_found == []
    projected = {pmid: (result["pub_year"], result["pub_month"], result["pub_day"]) for pmid, result in results.items()}
    assert projected == LIVE_DATE_EXPECTATIONS


# --- BULK ALTERNATIVE-IDENTIFIER LOOKUP ---
BULK_DOCUMENTS = {
    "PMID:30690000": {
        "pubmed": {
            **PUBMED_METADATA,
            "title": "First",
            "identifiers": ["doi:10.1000/first"],
        }
    },
    "PMID:17284678": {
        "pubmed": {
            **PUBMED_METADATA,
            "title": "Second",
            "identifiers": ["PMC:PMC1904490", "doi:10.1242/jcs.03153"],
        }
    },
}
BULK_IDENTIFIER_MAP = {
    "doi:10.1000/first": "PMID:30690000",
    "doi:10.1242/jcs.03153": "PMID:17284678",
    "pmc:pmc1904490": "PMID:17284678",
}


class _RecordingClient:
    """Minimal stand-in that records both lookup strategies exactly."""

    index = "annotator-pubmed"

    def __init__(self, documents=None, identifier_map=None, bulk_response=None, combined_response=None):
        self.documents = BULK_DOCUMENTS if documents is None else documents
        self.identifier_map = BULK_IDENTIFIER_MAP if identifier_map is None else identifier_map
        self.bulk_response = bulk_response
        self.combined_response = combined_response
        self.calls = []

    def _hit(self, document_id, query=None):
        hit = {**self.documents[document_id], "_id": document_id}
        if query is not None:
            hit["query"] = query
        return hit

    async def mget(self, ids, fields=None):
        self.calls.append(("mget", list(ids)))
        return [
            (
                self._hit(document_id, query=document_id)
                if document_id in self.documents
                else {"query": document_id, "notfound": True}
            )
            for document_id in ids
        ]

    async def querymany_exact(self, query_list, field, fields=None, size=None):
        self.calls.append(("querymany_exact", list(query_list)))
        results = []
        for query in query_list:
            document_id = self.identifier_map.get(query.lower())
            results.append(
                self._hit(document_id, query=query) if document_id is not None else {"query": query, "notfound": True}
            )
        return results

    async def search_terms(self, query_list, field, fields=None, size=None):
        self.calls.append(("search_terms", list(query_list)))
        if self.bulk_response is not None:
            return self.bulk_response
        document_ids = list(
            dict.fromkeys(self.identifier_map[query] for query in query_list if query in self.identifier_map)
        )
        hits = [self._hit(document_id) for document_id in reversed(document_ids)]
        return {"total": len(hits), "total_relation": "eq", "hits": hits}

    async def search_ids_or_terms(self, document_ids, query_list, field, fields=None, size=None):
        self.calls.append(
            (
                "search_ids_or_terms",
                {
                    "document_ids": list(document_ids),
                    "query_list": list(query_list),
                    "field": field,
                    "fields": fields,
                    "size": size,
                },
            )
        )
        if self.combined_response is not None:
            return self.combined_response

        requested_documents = set(document_ids)
        requested_alternatives = set(query_list)
        matching_document_ids = []
        for document_id, document in self.documents.items():
            identifiers = document.get("pubmed", {}).get("identifiers", [])
            normalized_identifiers = {identifier.lower() for identifier in identifiers if isinstance(identifier, str)}
            if document_id in requested_documents or normalized_identifiers & requested_alternatives:
                matching_document_ids.append(document_id)

        hits = []
        for document_id in reversed(matching_document_ids):
            hit = self._hit(document_id)
            matched_queries = []
            if document_id in requested_documents:
                matched_queries.append("document_ids")
            identifiers = hit.get("pubmed", {}).get("identifiers", [])
            if any(
                isinstance(identifier, str) and identifier.lower() in requested_alternatives
                for identifier in identifiers
            ):
                matched_queries.append("alternative_identifiers")
            hit["_matched_queries"] = matched_queries
            hits.append(hit)
        return {
            "timed_out": False,
            "terminated_early": False,
            "failed_shards": 0,
            "total": len(hits),
            "total_relation": "eq",
            "hits": hits,
        }

    def call_arguments(self, name):
        return [arguments for called, arguments in self.calls if called == name]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_lookup_runs_mget_and_search_concurrently_without_pruning():
    started = set()
    both_started = asyncio.Event()

    class ConcurrentClient(_RecordingClient):
        async def _arrive(self, method):
            started.add(method)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.1)

        async def mget(self, ids, fields=None):
            await self._arrive("mget")
            return await super().mget(ids, fields)

        async def search_terms(self, query_list, field, fields=None, size=None):
            await self._arrive("search_terms")
            return await super().search_terms(query_list, field, fields, size)

    client = ConcurrentClient()
    hits = await DocumentMetadataService._fetch_hits_bulk_search(
        client,
        ["PMID:30690000"],
        ["doi:10.1000/first", "doi:10.1242/jcs.03153"],
    )

    assert started == {"mget", "search_terms"}
    assert client.call_arguments("search_terms") == [["doi:10.1000/first", "doi:10.1242/jcs.03153"]]
    assert set(hits) == {"PMID:30690000", "doi:10.1000/first", "doi:10.1242/jcs.03153"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_lookup_fans_one_document_out_to_doi_pmcid_and_case_variants():
    client = _RecordingClient()
    submitted = ["DOI:10.1242/JCS.03153", "doi:10.1242/jcs.03153", "pmc:PMC1904490"]

    hits = await DocumentMetadataService._fetch_hits_bulk_search(client, [], submitted)

    assert client.call_arguments("search_terms") == [["doi:10.1242/jcs.03153", "pmc:pmc1904490"]]
    assert set(hits) == set(submitted)
    assert {hit["_id"] for hit in hits.values()} == {"PMID:17284678"}
    assert client.call_arguments("querymany_exact") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_lookup_maps_nonoverlapping_hits_independent_of_hit_order():
    client = _RecordingClient()
    submitted = ["doi:10.1000/first", "doi:10.1242/jcs.03153"]

    hits = await DocumentMetadataService._fetch_hits_bulk_search(client, [], submitted)

    assert hits[submitted[0]]["pubmed"]["title"] == "First"
    assert hits[submitted[1]]["pubmed"]["title"] == "Second"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_lookup_preserves_result_and_not_found_order(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: client,
    )
    submitted = [MISSING_DOI, PMID, DOI, "doi:10.9999/also-absent"]

    results, not_found = await DocumentMetadataService(
        elasticsearch_connection="in_cluster",
        lookup_strategy=BULK_SEARCH_LOOKUP_STRATEGY,
    ).get_publications(submitted)

    assert list(results) == [PMID, DOI]
    assert not_found == [MISSING_DOI, "doi:10.9999/also-absent"]


def _fallback_hit(query):
    return {**BULK_DOCUMENTS["PMID:17284678"], "_id": "PMID:17284678", "query": query}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bulk_response",
    [
        {
            "total": 2,
            "total_relation": "eq",
            "hits": [{**BULK_DOCUMENTS["PMID:17284678"], "_id": "PMID:17284678"}],
        },
        {
            "total": 1,
            "total_relation": "gte",
            "hits": [{**BULK_DOCUMENTS["PMID:17284678"], "_id": "PMID:17284678"}],
        },
        {
            "timed_out": True,
            "total": 1,
            "total_relation": "eq",
            "hits": [{**BULK_DOCUMENTS["PMID:17284678"], "_id": "PMID:17284678"}],
        },
        {
            "failed_shards": 1,
            "total": 1,
            "total_relation": "eq",
            "hits": [{**BULK_DOCUMENTS["PMID:17284678"], "_id": "PMID:17284678"}],
        },
        {"total": 1, "total_relation": "eq", "hits": [{"_id": "PMID:17284678", "pubmed": {}}]},
        {
            "total": 1,
            "total_relation": "eq",
            "hits": [
                {
                    "_id": "PMID:17284678",
                    "pubmed": {"identifiers": ["doi:10.9999/unrequested"]},
                }
            ],
        },
    ],
    ids=[
        "truncated",
        "inexact-total",
        "timed-out",
        "failed-shard",
        "malformed-identifiers",
        "unassignable-hit",
    ],
)
async def test_bulk_lookup_falls_back_to_exact_msearch_when_reverse_mapping_is_unsafe(bulk_response):
    client = _RecordingClient(bulk_response=bulk_response)

    hits = await DocumentMetadataService._fetch_hits_bulk_search(client, [], [DOI])

    assert hits[DOI] == _fallback_hit(DOI)
    assert client.call_arguments("querymany_exact") == [[DOI]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_lookup_falls_back_when_one_identifier_belongs_to_multiple_documents():
    collision = "doi:10.1000/collision"
    pmcid = "PMC:PMC1904490"
    documents = {
        "PMID:1": {"pubmed": {"title": "Wrong", "identifiers": [collision]}},
        "PMID:2": {"pubmed": {"title": "Right", "identifiers": [collision, pmcid]}},
    }
    identifier_map = {collision: "PMID:2", pmcid.lower(): "PMID:2"}
    bulk_response = {
        "total": 2,
        "total_relation": "eq",
        "hits": [
            {**documents["PMID:1"], "_id": "PMID:1"},
            {**documents["PMID:2"], "_id": "PMID:2"},
        ],
    }
    client = _RecordingClient(documents=documents, identifier_map=identifier_map, bulk_response=bulk_response)

    hits = await DocumentMetadataService._fetch_hits_bulk_search(client, [], [collision, pmcid])

    assert hits[collision]["_id"] == "PMID:2"
    assert hits[pmcid]["_id"] == "PMID:2"
    assert client.call_arguments("querymany_exact") == [[collision, pmcid]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_and_current_lookup_agree_on_a_mixed_batch():
    document_ids = ["PMID:30690000"]
    search_ids = [DOI, PMCID, MISSING_DOI]

    current = await DocumentMetadataService._fetch_hits(_RecordingClient(), document_ids, search_ids)
    bulk = await DocumentMetadataService._fetch_hits_bulk_search(_RecordingClient(), document_ids, search_ids)

    assert sorted(bulk) == sorted(current)
    for key in bulk:
        assert bulk[key]["pubmed"] == current[key]["pubmed"]


# --- ONE-REQUEST COMBINED LOOKUP ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_uses_one_search_and_fans_out_every_identifier_spelling():
    client = _RecordingClient()
    document_ids = ["PMID:30690000"]
    search_ids = [
        "DOI:10.1000/FIRST",
        "doi:10.1000/first",
        "DOI:10.1242/JCS.03153",
        "pmc:PMC1904490",
    ]

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, document_ids, search_ids)

    assert client.call_arguments("search_ids_or_terms") == [
        {
            "document_ids": document_ids,
            "query_list": [
                "doi:10.1000/first",
                "doi:10.1242/jcs.03153",
                "pmc:pmc1904490",
            ],
            "field": "pubmed.identifiers",
            "fields": ["pubmed"],
            "size": 4,
        }
    ]
    assert client.call_arguments("mget") == []
    assert client.call_arguments("querymany_exact") == []
    assert set(hits) == {"PMID:30690000", *search_ids}
    assert hits["PMID:30690000"]["_id"] == "PMID:30690000"
    assert hits["DOI:10.1000/FIRST"]["_id"] == "PMID:30690000"
    assert {hits[identifier]["_id"] for identifier in search_ids[2:]} == {"PMID:17284678"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_accepts_a_pmid_only_hit_without_alternate_identifiers():
    document_id = "PMID:30690000"
    client = _RecordingClient(documents={document_id: {"pubmed": PUBMED_METADATA}}, identifier_map={})

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, [document_id], [])

    assert hits[document_id]["pubmed"] == PUBMED_METADATA
    assert client.call_arguments("search_ids_or_terms")[0]["size"] == 1
    assert client.call_arguments("mget") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_reuses_the_bulk_strategy_for_an_all_alternate_batch():
    client = _RecordingClient()
    search_ids = ["DOI:10.1242/JCS.03153", "pmc:PMC1904490"]

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, [], search_ids)

    assert set(hits) == set(search_ids)
    assert client.call_arguments("search_terms") == [["doi:10.1242/jcs.03153", "pmc:pmc1904490"]]
    assert client.call_arguments("search_ids_or_terms") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_preserves_result_and_not_found_order(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: client,
    )
    submitted = [MISSING_DOI, "pmid:30690000", DOI, "doi:10.9999/also-absent", PMCID]

    results, not_found = await DocumentMetadataService(
        elasticsearch_connection="in_cluster",
        lookup_strategy=COMBINED_SEARCH_LOOKUP_STRATEGY,
    ).get_publications(submitted)

    assert list(results) == ["pmid:30690000", DOI, PMCID]
    assert not_found == [MISSING_DOI, "doi:10.9999/also-absent"]
    assert len(client.call_arguments("search_ids_or_terms")) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_caps_the_search_window_at_the_endpoint_limit():
    client = _RecordingClient(documents={}, identifier_map={})
    document_ids = [f"PMID:{index}" for index in range(1, 102)]

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, document_ids, [])

    assert hits == {}
    assert client.call_arguments("search_ids_or_terms")[0]["size"] == 100


def _combined_hit(document_id, matched_queries, pubmed=None):
    return {
        "_id": document_id,
        "pubmed": BULK_DOCUMENTS[document_id]["pubmed"] if pubmed is None else pubmed,
        "_matched_queries": matched_queries,
    }


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "combined_response",
    [
        {
            "total": 2,
            "total_relation": "eq",
            "hits": [_combined_hit("PMID:30690000", ["document_ids"])],
        },
        {
            "total": 1,
            "total_relation": "gte",
            "hits": [_combined_hit("PMID:30690000", ["document_ids"])],
        },
        {
            "timed_out": True,
            "total": 1,
            "total_relation": "eq",
            "hits": [_combined_hit("PMID:30690000", ["document_ids"])],
        },
        {
            "terminated_early": True,
            "total": 1,
            "total_relation": "eq",
            "hits": [_combined_hit("PMID:30690000", ["document_ids"])],
        },
        {
            "failed_shards": 1,
            "total": 1,
            "total_relation": "eq",
            "hits": [_combined_hit("PMID:30690000", ["document_ids"])],
        },
        {
            "total": 1,
            "total_relation": "eq",
            "hits": [_combined_hit("PMID:30690000", None)],
        },
        {
            "total": 1,
            "total_relation": "eq",
            "hits": [
                _combined_hit(
                    "PMID:17284678",
                    ["alternative_identifiers"],
                    pubmed={"identifiers": "doi:10.1242/jcs.03153"},
                )
            ],
        },
        {
            "total": 1,
            "total_relation": "eq",
            "hits": [_combined_hit("PMID:17284678", ["unknown_clause"])],
        },
    ],
    ids=[
        "truncated",
        "inexact-total",
        "timed-out",
        "terminated-early",
        "failed-shard",
        "missing-attribution",
        "malformed-identifiers",
        "unknown-attribution",
    ],
)
async def test_combined_lookup_falls_back_for_the_whole_request_when_results_are_unsafe(combined_response):
    client = _RecordingClient(combined_response=combined_response)

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, [PMID], [DOI])

    assert hits[PMID]["_id"] == PMID
    assert hits[DOI]["_id"] == "PMID:17284678"
    assert client.call_arguments("mget") == [[PMID]]
    assert client.call_arguments("querymany_exact") == [[DOI]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_falls_back_when_one_alternate_identifier_has_two_owners():
    collision = "doi:10.1000/collision"
    documents = {
        "PMID:1": {"pubmed": {"title": "Wrong", "identifiers": [collision]}},
        "PMID:2": {"pubmed": {"title": "Right", "identifiers": [collision]}},
    }
    combined_response = {
        "total": 2,
        "total_relation": "eq",
        "timed_out": False,
        "failed_shards": 0,
        "hits": [
            {
                **documents["PMID:1"],
                "_id": "PMID:1",
                "_matched_queries": ["document_ids", "alternative_identifiers"],
            },
            {
                **documents["PMID:2"],
                "_id": "PMID:2",
                "_matched_queries": ["alternative_identifiers"],
            },
        ],
    }
    client = _RecordingClient(
        documents=documents,
        identifier_map={collision: "PMID:2"},
        combined_response=combined_response,
    )

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, ["PMID:1"], [collision])

    assert hits[collision]["_id"] == "PMID:2"
    assert client.call_arguments("mget") == [["PMID:1"]]
    assert client.call_arguments("querymany_exact") == [[collision]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_lookup_uses_current_strategy_for_non_ascii_alternates():
    identifier = "doi:10.1000/café"
    client = _RecordingClient(identifier_map={identifier: "PMID:30690000"})

    hits = await DocumentMetadataService._fetch_hits_combined_search(client, [PMID], [identifier])

    assert hits[PMID]["_id"] == PMID
    assert hits[identifier]["_id"] == "PMID:30690000"
    assert client.call_arguments("search_ids_or_terms") == []
    assert client.call_arguments("mget") == [[PMID]]
    assert client.call_arguments("querymany_exact") == [[identifier]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_combined_and_current_lookup_agree_on_a_mixed_batch():
    document_ids = ["PMID:30690000"]
    search_ids = [DOI, PMCID, MISSING_DOI]

    current = await DocumentMetadataService._fetch_hits(_RecordingClient(), document_ids, search_ids)
    combined = await DocumentMetadataService._fetch_hits_combined_search(
        _RecordingClient(),
        document_ids,
        search_ids,
    )

    assert sorted(combined) == sorted(current)
    for key in combined:
        assert combined[key]["pubmed"] == current[key]["pubmed"]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup_strategy, publication_ids",
    [
        (CURRENT_LOOKUP_STRATEGY, [PMID, DOI]),
        (BULK_SEARCH_LOOKUP_STRATEGY, [PMID, DOI]),
        (COMBINED_SEARCH_LOOKUP_STRATEGY, [PMID, DOI]),
        (COMBINED_SEARCH_LOOKUP_STRATEGY, [DOI, PMCID]),
    ],
)
async def test_lookup_execution_metadata_reports_no_fallback_for_normal_routes(
    monkeypatch,
    lookup_strategy,
    publication_ids,
):
    client = _RecordingClient()
    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: client,
    )

    results, not_found, lookup_fallback = await DocumentMetadataService(
        elasticsearch_connection="in_cluster",
        lookup_strategy=lookup_strategy,
    ).get_publications_with_metadata(publication_ids)

    assert set(results) == set(publication_ids)
    assert not_found == []
    assert lookup_fallback is False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup_strategy, publication_ids",
    [
        (BULK_SEARCH_LOOKUP_STRATEGY, ["doi:10.1000/café"]),
        (COMBINED_SEARCH_LOOKUP_STRATEGY, ["doi:10.1000/café"]),
        (COMBINED_SEARCH_LOOKUP_STRATEGY, [PMID, "doi:10.1000/café"]),
    ],
)
async def test_lookup_execution_metadata_does_not_label_deterministic_non_ascii_routing_as_fallback(
    monkeypatch,
    lookup_strategy,
    publication_ids,
):
    identifier = "doi:10.1000/café"
    client = _RecordingClient(identifier_map={identifier: PMID})
    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: client,
    )

    _, not_found, lookup_fallback = await DocumentMetadataService(
        elasticsearch_connection="in_cluster",
        lookup_strategy=lookup_strategy,
    ).get_publications_with_metadata(publication_ids)

    assert not_found == []
    assert lookup_fallback is False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("lookup_strategy", [BULK_SEARCH_LOOKUP_STRATEGY, COMBINED_SEARCH_LOOKUP_STRATEGY])
async def test_lookup_execution_metadata_marks_rejected_speculative_responses_as_fallback(
    monkeypatch,
    lookup_strategy,
):
    unsafe_response = {"total": 1, "total_relation": "gte", "hits": []}
    client = _RecordingClient(
        bulk_response=unsafe_response,
        combined_response=unsafe_response,
    )
    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: client,
    )

    results, not_found, lookup_fallback = await DocumentMetadataService(
        elasticsearch_connection="in_cluster",
        lookup_strategy=lookup_strategy,
    ).get_publications_with_metadata([PMID, DOI])

    assert set(results) == {PMID, DOI}
    assert not_found == []
    assert lookup_fallback is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lookup_fallback_metadata_stays_bound_to_overlapping_requests(monkeypatch):
    both_started = asyncio.Event()
    arrivals = 0

    class OverlapClient(_RecordingClient):
        async def search_terms(self, query_list, field, fields=None, size=None):
            nonlocal arrivals
            self.calls.append(("search_terms", list(query_list)))
            arrivals += 1
            if arrivals == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.1)
            if query_list == [DOI]:
                return {"total": 1, "total_relation": "gte", "hits": []}
            return await super().search_terms(query_list, field, fields, size)

    client = OverlapClient()
    monkeypatch.setattr(
        "biothings_annotator.annotator.document_metadata.get_elasticsearch_client",
        lambda node_type, elasticsearch_connection: client,
    )
    service = DocumentMetadataService(
        elasticsearch_connection="in_cluster",
        lookup_strategy=BULK_SEARCH_LOOKUP_STRATEGY,
    )

    fallback_result, normal_result = await asyncio.gather(
        service.get_publications_with_metadata([DOI]),
        service.get_publications_with_metadata(["doi:10.1000/first"]),
    )

    assert fallback_result[2] is True
    assert normal_result[2] is False
    assert set(fallback_result[0]) == {DOI}
    assert set(normal_result[0]) == {"doi:10.1000/first"}


@pytest.mark.unit
def test_document_metadata_lookup_strategy_defaults_and_validation():
    assert DocumentMetadataService().lookup_strategy == CURRENT_LOOKUP_STRATEGY
    assert (
        DocumentMetadataService(lookup_strategy=BULK_SEARCH_LOOKUP_STRATEGY).lookup_strategy
        == BULK_SEARCH_LOOKUP_STRATEGY
    )
    assert (
        DocumentMetadataService(lookup_strategy=COMBINED_SEARCH_LOOKUP_STRATEGY).lookup_strategy
        == COMBINED_SEARCH_LOOKUP_STRATEGY
    )
    with pytest.raises(ValueError, match="lookup_strategy"):
        DocumentMetadataService(lookup_strategy="unknown")
