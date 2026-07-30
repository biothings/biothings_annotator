"""
Exercises the query methods within the biothings_annotator package
"""

import asyncio
import json
import logging
import random
from typing import Dict, List

import biothings_client
import httpx
import pytest

from biothings_annotator import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings, utils
from biothings_annotator.annotator.exceptions import SourceDiscoveryError
from biothings_annotator.annotator.settings import SERVICE_PROVIDER_API_HOST

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.unit
@pytest.mark.parametrize("node_type", ["gene", "chem", "disease", "NULL"])
def test_annotation_client(node_type: str):
    """
    Tests accessing different flavors of the biothings client from within the scope of the annotator
    instance

    If a valid keyword for the node is provided, then we'll yield an instance of the
    biothings_client for accessing nodes of that type

    Otherwise we raise a KeyError attempting to access a node type that doesn't exist for the
    biothings client
    """
    if node_type in ANNOTATOR_CLIENTS.keys():
        client = utils.get_client(node_type, SERVICE_PROVIDER_API_HOST)
        assert isinstance(client, biothings_client.AsyncBiothingClient)
    else:
        with pytest.raises(ValueError):
            utils.get_client(node_type, SERVICE_PROVIDER_API_HOST)


@pytest.mark.unit
def test_endpoint_annotation_client_uses_configured_url(monkeypatch):
    """
    Endpoint-backed clients should be built from SERVICE_PROVIDER_API_HOST without
    requiring the live metadata endpoint in this unit test.
    """
    client_parameters = ANNOTATOR_CLIENTS["phenotype"]["client"]
    original_instance = client_parameters.get("instance")
    original_cache_key = client_parameters.get("instance_cache_key")
    had_cache_key = "instance_cache_key" in client_parameters
    fake_client = object()
    calls = []

    def fake_get_async_client(**kwargs):
        calls.append(kwargs)
        return fake_client

    try:
        client_parameters["instance"] = None
        client_parameters.pop("instance_cache_key", None)
        monkeypatch.setattr(biothings_client, "get_async_client", fake_get_async_client)

        client = utils.get_client("phenotype", SERVICE_PROVIDER_API_HOST)
    finally:
        client_parameters["instance"] = original_instance
        if had_cache_key:
            client_parameters["instance_cache_key"] = original_cache_key
        else:
            client_parameters.pop("instance_cache_key", None)

    assert client is fake_client
    assert calls == [
        {
            "biothing_type": None,
            "instance": True,
            "url": f"{SERVICE_PROVIDER_API_HOST}/hpo",
        }
    ]


@pytest.mark.unit
def test_endpoint_annotation_client_returns_none_on_metadata_failure(monkeypatch):
    """
    BioThings endpoint client construction reads remote metadata. If that remote
    service is down or returns non-JSON, the caller should get None instead of a
    leaked metadata parsing exception.
    """
    client_parameters = ANNOTATOR_CLIENTS["phenotype"]["client"]
    original_instance = client_parameters.get("instance")
    original_cache_key = client_parameters.get("instance_cache_key")
    had_cache_key = "instance_cache_key" in client_parameters

    def fail_get_async_client(**kwargs):
        raise json.JSONDecodeError("Expecting value", "", 0)

    try:
        client_parameters["instance"] = None
        client_parameters.pop("instance_cache_key", None)
        monkeypatch.setattr(biothings_client, "get_async_client", fail_get_async_client)

        client = utils.get_client("phenotype", SERVICE_PROVIDER_API_HOST)
    finally:
        client_parameters["instance"] = original_instance
        if had_cache_key:
            client_parameters["instance_cache_key"] = original_cache_key
        else:
            client_parameters.pop("instance_cache_key", None)

    assert client is None


@pytest.mark.unit
def test_source_named_endpoint_client_avoids_metadata_probe_and_normalizes_host(monkeypatch):
    client_parameters = ANNOTATOR_CLIENTS["pubmed"]["client"]
    original_instance = client_parameters.get("instance")
    original_cache_key = client_parameters.get("instance_cache_key")
    had_cache_key = "instance_cache_key" in client_parameters
    fake_client = object()
    calls = []

    def fake_get_async_client(**kwargs):
        calls.append(kwargs)
        return fake_client

    try:
        client_parameters["instance"] = None
        client_parameters.pop("instance_cache_key", None)
        monkeypatch.setattr(biothings_client, "get_async_client", fake_get_async_client)

        client = utils.get_client("pubmed", f"{SERVICE_PROVIDER_API_HOST}/")
    finally:
        client_parameters["instance"] = original_instance
        if had_cache_key:
            client_parameters["instance_cache_key"] = original_cache_key
        else:
            client_parameters.pop("instance_cache_key", None)

    assert client is fake_client
    assert calls == [
        {
            "biothing_type": "pubmed",
            "instance": True,
            "url": f"{SERVICE_PROVIDER_API_HOST}/pubmed",
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_biothings_sources_validates_authoritative_source_list():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{SERVICE_PROVIDER_API_HOST}/api/list"
        assert request.headers["Cache-Control"] == "no-cache"
        return httpx.Response(200, json=["gene", "pubmed"], request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        sources = await utils.fetch_biothings_sources(
            SERVICE_PROVIDER_API_HOST,
            http_client=http_client,
        )

    assert sources == frozenset({"gene", "pubmed"})


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,payload",
    [
        (503, {"error": "unavailable"}),
        (200, {"pubmed": True}),
        (200, ["pubmed", 42]),
    ],
)
async def test_fetch_biothings_sources_rejects_unknown_discovery_state(status_code, payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(SourceDiscoveryError):
            await utils.fetch_biothings_sources(
                SERVICE_PROVIDER_API_HOST,
                http_client=http_client,
            )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "malformed_json"])
async def test_fetch_biothings_sources_rejects_transport_and_json_failures(failure):
    async def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("source discovery timed out", request=request)
        return httpx.Response(200, content=b"{not-json", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(SourceDiscoveryError):
            await utils.fetch_biothings_sources(
                SERVICE_PROVIDER_API_HOST,
                http_client=http_client,
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_source_cache_refreshes_and_briefly_backs_off_failures(monkeypatch):
    clock = {"now": 100.0}
    fetched_sources = [
        frozenset(),
        SourceDiscoveryError(),
        frozenset({"pubmed"}),
    ]
    fetch_calls = []

    async def fake_fetch(api_host):
        fetch_calls.append(api_host)
        result = fetched_sources.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(utils, "fetch_biothings_sources", fake_fetch)
    monkeypatch.setattr(utils.time, "monotonic", lambda: clock["now"])
    utils.clear_biothings_source_cache()
    try:
        assert await utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST) == frozenset()
        clock["now"] += utils.BIOTHINGS_SOURCE_DISCOVERY_TTL - 1
        assert await utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST) == frozenset()
        assert fetch_calls == [SERVICE_PROVIDER_API_HOST]

        clock["now"] += 2
        with pytest.raises(SourceDiscoveryError):
            await utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST)
        with pytest.raises(SourceDiscoveryError):
            await utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST)
        assert fetch_calls == [
            SERVICE_PROVIDER_API_HOST,
            SERVICE_PROVIDER_API_HOST,
        ]

        clock["now"] += utils.BIOTHINGS_SOURCE_DISCOVERY_ERROR_TTL + 1
        assert await utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST) == frozenset({"pubmed"})
        assert fetch_calls == [
            SERVICE_PROVIDER_API_HOST,
            SERVICE_PROVIDER_API_HOST,
            SERVICE_PROVIDER_API_HOST,
        ]
    finally:
        utils.clear_biothings_source_cache()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_biothings_source_cache_shares_concurrent_refresh(monkeypatch):
    release_refresh = asyncio.Event()
    fetch_calls = []

    async def fake_fetch(api_host):
        fetch_calls.append(api_host)
        await release_refresh.wait()
        return frozenset({"pubmed"})

    monkeypatch.setattr(utils, "fetch_biothings_sources", fake_fetch)
    utils.clear_biothings_source_cache()
    try:
        requests = [asyncio.create_task(utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST)) for _ in range(20)]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert fetch_calls == [SERVICE_PROVIDER_API_HOST]

        release_refresh.set()
        assert await asyncio.gather(*requests) == [frozenset({"pubmed"})] * 20
    finally:
        release_refresh.set()
        utils.clear_biothings_source_cache()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_biothings_source_cache_cancels_inflight_refresh(monkeypatch):
    first_refresh_started = asyncio.Event()
    first_refresh_cancelled = asyncio.Event()
    first_refresh_release = asyncio.Event()
    second_refresh_started = asyncio.Event()
    second_refresh_release = asyncio.Event()
    fetch_calls = []

    async def fake_fetch(api_host):
        fetch_calls.append(api_host)
        if len(fetch_calls) == 1:
            first_refresh_started.set()
            try:
                await first_refresh_release.wait()
            except asyncio.CancelledError:
                first_refresh_cancelled.set()
                await first_refresh_release.wait()
            return frozenset({"stale"})

        second_refresh_started.set()
        await second_refresh_release.wait()
        return frozenset({"pubmed"})

    monkeypatch.setattr(utils, "fetch_biothings_sources", fake_fetch)
    utils.clear_biothings_source_cache()
    requests = []
    try:
        stale_request = asyncio.create_task(utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST))
        requests.append(stale_request)
        await first_refresh_started.wait()
        utils.clear_biothings_source_cache()
        await first_refresh_cancelled.wait()

        fresh_request = asyncio.create_task(utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST))
        requests.append(fresh_request)
        await second_refresh_started.wait()
        normalized_host = SERVICE_PROVIDER_API_HOST.rstrip("/")
        refresh_key = (id(asyncio.get_running_loop()), normalized_host)
        second_refresh_task = utils._biothings_source_refreshes[refresh_key]

        joined_request = asyncio.create_task(utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST))
        requests.append(joined_request)
        await asyncio.sleep(0)
        assert fetch_calls == [
            SERVICE_PROVIDER_API_HOST,
            SERVICE_PROVIDER_API_HOST,
        ]

        first_refresh_release.set()
        assert await stale_request == frozenset({"stale"})
        assert utils._biothings_source_cache == {}
        assert utils._biothings_source_refreshes[refresh_key] is second_refresh_task

        second_refresh_release.set()
        assert await asyncio.gather(fresh_request, joined_request) == [
            frozenset({"pubmed"}),
            frozenset({"pubmed"}),
        ]
    finally:
        first_refresh_release.set()
        second_refresh_release.set()
        for request in requests:
            if not request.done():
                request.cancel()
        await asyncio.gather(*requests, return_exceptions=True)
        utils.clear_biothings_source_cache()
        await asyncio.sleep(0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "search_keyword, collection, histogram",
    [
        (
            "entry",
            [{"entry": "compilation", "status": "NORMAL", "_id": 82}],
            {"compilation": [{"entry": "compilation", "status": "NORMAL", "_id": 82}]},
        ),
        (
            "entry",
            [
                {"entry": "linker", "status": "NORMAL", "_id": 23},
                {"entry": "builder", "status": "WARNING", "_id": 3},
                {"entry": "builder", "status": "WARNING", "_id": 8},
                {"entry": "builder", "status": "NORMAL", "_id": 92},
                {"entry": "compilation", "status": "WARNING", "_id": 55},
                {"entry": "compilation", "status": "NORMAL", "_id": 80},
                {"entry": "runtime", "status": "NORMAL", "_id": 80},
                {"entry": "runtime", "status": "WARNING", "_id": 83},
                {"entry": "runtime", "status": "ERROR", "_id": 99},
                {"entry": "cleanup", "status": "NORMAL", "_id": 1},
                {"entry": "cleanup", "status": "NORMAL", "_id": 10},
            ],
            {
                "linker": [{"entry": "linker", "status": "NORMAL", "_id": 23}],
                "builder": [
                    {"entry": "builder", "status": "WARNING", "_id": 3},
                    {"entry": "builder", "status": "WARNING", "_id": 8},
                    {"entry": "builder", "status": "NORMAL", "_id": 92},
                ],
                "compilation": [
                    {"entry": "compilation", "status": "WARNING", "_id": 55},
                    {"entry": "compilation", "status": "NORMAL", "_id": 80},
                ],
                "runtime": [
                    {"entry": "runtime", "status": "NORMAL", "_id": 80},
                    {"entry": "runtime", "status": "WARNING", "_id": 83},
                    {"entry": "runtime", "status": "ERROR", "_id": 99},
                ],
                "cleanup": [
                    {"entry": "cleanup", "status": "NORMAL", "_id": 1},
                    {"entry": "cleanup", "status": "NORMAL", "_id": 10},
                ],
            },
        ),
        ("NULL", [{"entry": "compilation", "status": "NORMAL", "_id": 82}], {}),
        ("NULL", [{}], {}),
        ("NULL", [], {}),
        ("", [{}], {}),
    ],
)
def test_query_post_processing(search_keyword: str, collection: List[Dict], histogram: Dict):
    """
    Evaluates the group_by_subfield helper function for creating a dictionary histrogram of the
    based off the aggregated collection of dictionaries sharing a common key.

    Parameterized tests
    1) single-length entry
    2) multi-length entry
    3) search key not found
    4) empty collection (1)
    5) empty collection (2)
    6) empty collection and empty search key
    """
    histogram_response = utils.group_by_subfield(collection=collection, search_key=search_keyword)
    assert isinstance(histogram_response, dict)
    assert histogram_response == histogram


@pytest.mark.asyncio(scope="session")
@pytest.mark.parametrize(
    "curie_prefix",
    [
        prefix
        for prefix, prefix_settings in BIOLINK_PREFIX_to_BioThings.items()
        if "biothings" in prefix_settings.get("query_backends", ("biothings", "elasticsearch"))
    ],
)
async def test_biothings_query(curie_prefix: str):
    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    node_type, node_id = utils.parse_curie(curie=curie_query, return_type=True, return_id=True)

    domain_fields = ANNOTATOR_CLIENTS[node_type]["fields"]
    source = ANNOTATOR_CLIENTS[node_type]["client"].get("source")
    if source and source not in await utils.get_biothings_sources(SERVICE_PROVIDER_API_HOST):
        pytest.skip(f"BioThings source is not deployed: {source}")

    client = utils.get_client(node_type, SERVICE_PROVIDER_API_HOST)
    if not client:
        logger.warning("Failed to get the biothings client for %s type. This type is skipped.", node_type)
        return {}

    fields = ANNOTATOR_CLIENTS[node_type]["fields"]
    scopes = ANNOTATOR_CLIENTS[node_type]["scopes"]
    querymany_result = await client.querymany([node_id], scopes=scopes, fields=fields)
    logger.info("Done. %s annotation objects returned.", len(querymany_result))
    query_response = utils.group_by_subfield(collection=querymany_result, search_key="query")

    assert isinstance(query_response, dict)
    logger.info((f"Query Response: {query_response}" f"Query Fields: {domain_fields}"))
