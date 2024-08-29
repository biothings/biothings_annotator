"""
Application specific data for validating the web server

Particularly for testing larger concurrent queries and validating
that expected user queries are handled accordingly. In response
to the 502 gateway error's we've been receiving. These tests are
to validate that we should experience the same results against local
versus the CI environment | https://biothings.ci.transltr.io

"""

import asyncio
import json
import multiprocessing
import random
import uuid

import httpx
import pytest
import sanic


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_store",
    [
        [
            "cleaned_annotator_logs.json",
        ]
    ],
    indirect=True,
)
async def test_integration_server_responses(test_annotator: sanic.Sanic, data_store: dict):
    """
    Takes a cleaned up annotation log and creates a batch of queries
    from actual usage and asynchronously hits both the local and
    integration server

    It then compares the responses between the two for any discrepancies.
    """
    for user_query in data_store:
        user_query["identifer"] = str(uuid.uuid4())

    local_responses = {}
    for user_query in data_store:
        request = user_query["request"]
        method, endpoint, http_version = request.split(" ")
        body = user_query["body"]

        data = None
        if body != "":
            data = json.loads(body)

        request, response = await test_annotator.asgi_client.request(method=method, url=endpoint, json=data)
        local_responses[user_query["identifier"]] = response
        random_delay = random.random() * 1e-3
        await asyncio.sleep(random_delay)

    integration_responses = {}
    integration_client = httpx.AsyncClient()
    integration_url = "https://biothings.ci.transltr.io"
    for user_query in data_store:
        request = user_query["request"]
        method, endpoint, http_version = request.split(" ")
        body = user_query["body"]

        data = None
        if body != "":
            data = json.loads(body)

        url = f"{integration_url}/{endpoint}"
        request, response = await integration_client.request(method=method, url=url, content=data)
        integration_responses[user_query["identifier"]] = response
        random_delay = random.random() * 1e-3
        await asyncio.sleep(random_delay)

    unique_identifers = [user_query["identifier"] for user_query in data_store]
    for unique_identifier in unique_identifers:
        local_response = local_responses[unique_identifier]
        integration_response = integration_responses[unique_identifier]

        assert local_response.body == integration_response.body
        assert local_response.status_code == integration_response.status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_store, num_workers",
    [
        [
            "cleaned_annotator_logs.json",
            "cleaned_annotator_logs.json",
            "cleaned_annotator_logs.json",
        ],
        [4, 8, 16],
    ],
    indirect=True,
)
async def test_multiple_users_querying(test_annotator: sanic.Sanic, data_store: dict, num_workers: int):
    """
    Similar to the `test_integration_server_responses` test, however we now want to test it a
    multiprocessing flavor to attempt to simular multiple users at once hitting the server
    """
    for user_query in data_store:
        user_query["identifer"] = str(uuid.uuid4())

    local_futures = {}
    with multiprocessing.Pool(num_workers) as worker_pool:
        for user_query in data_store:
            request = user_query["request"]
            method, endpoint, http_version = request.split(" ")
            body = user_query["body"]

            data = None
            if body != "":
                data = json.loads(body)

            worker_request_arguments = {"method": method, "url": endpoint, "json": data}

            async_local_future = worker_pool.apply_async(
                test_annotator.asgi_client.request, kwds=worker_request_arguments
            )
            local_futures[user_query["identifier"]] = async_local_future
            random_delay = random.random() * 1e-3
            await asyncio.sleep(random_delay)

    integration_futures = {}
    integration_client = httpx.AsyncClient()
    integration_url = "https://biothings.ci.transltr.io"
    with multiprocessing.Pool(num_workers) as worker_pool:
        for user_query in data_store:
            request = user_query["request"]
            method, endpoint, http_version = request.split(" ")
            body = user_query["body"]

            data = None
            if body != "":
                data = json.loads(body)

            worker_request_arguments = {"method": method, "url": f"{integration_url}/{endpoint}", "content": data}

            async_integration_future = worker_pool.apply_async(
                integration_client.request, kwds=worker_request_arguments
            )

            integration_futures[user_query["identifer"]] = async_integration_future
            random_delay = random.random() * 1e-3
            await asyncio.sleep(random_delay)

    unique_identifers = [user_query["identifier"] for user_query in data_store]
    for unique_identifier in unique_identifers:
        local_future = local_futures[unique_identifier]
        integration_future = integration_futures[unique_identifier]

        local_response = local_future.get()
        integration_response = integration_future.get()

        assert local_response.body == integration_response.body
        assert local_response.status_code == integration_response.status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_store",
    [
        [
            "ara/ara-aragorn_annotator_nodes.json"
            "ara/ara-bte_annotator_nodes.json"
            "ara/ara-improving_annotator_nodes.json"
            "ara/ara-unsecret_annotator_nodes.json"
        ],
    ],
    indirect=True,
)
async def test_ara_integration_trapi_requests(test_annotator: sanic.Sanic, data_store: dict):
    """
    Similar to the `test_integration_server_responses` test, however we now want to test it a
    multiprocessing flavor to attempt to simular multiple users at once hitting the server
    """
    num_workers = random.sample([4, 8, 16], k=1)
    integration_futures = []
    integration_client = httpx.AsyncClient()
    integration_url = "https://biothings.ci.transltr.io"
    worker_request_arguments = {"method": "POST", "url": f"{integration_url}/trapi/", "json": data_store}

    with multiprocessing.Pool(num_workers) as worker_pool:
        for worker in range(num_workers):
            async_integration_future = worker_pool.apply_async(
                integration_client.request, kwds=worker_request_arguments
            )
            integration_futures.append(async_integration_future)
            random_delay = random.random() * 1e-3
            await asyncio.sleep(random_delay)

    for ara_future in integration_futures:
        ara_response = ara_future.get()
        assert ara_response.status_code == 200
