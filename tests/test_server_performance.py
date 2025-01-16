"""
Application specific data for validating the web server

Particularly for testing larger concurrent queries and validating
that expected user queries are handled accordingly. In response
to the 502 gateway error's we've been receiving. These tests are
to validate that we should experience the same results against local
versus the CI environment | https://annotator.ci.transltr.io

"""

from pathlib import Path
from typing import Union
import asyncio
import collections
import json
import logging
import multiprocessing
import random
import time
import uuid

import httpx
import pytest
import sanic


logger = logging.getLogger(__name__)


@pytest.mark.performance
@pytest.mark.asyncio
@pytest.mark.parametrize("data_store", ["cleaned_annotator_logs.json"])
async def test_integration_server_responses(
    temporary_data_storage: Union[str, Path],
    test_annotator: sanic.Sanic,
    data_store: str,
):
    """
    Takes a cleaned up annotation log and creates a batch of queries
    from actual usage and asynchronously hits both the local and
    integration server

    It then compares the responses between the two for any discrepancies.
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        query_list = json.load(file_handle)

    for user_query in query_list:
        user_query["identifier"] = str(uuid.uuid4())

    local_responses = {}
    integration_responses = {}
    integration_client = httpx.AsyncClient()
    integration_url = "https://annotator.ci.transltr.io"

    for user_query in query_list:
        http_request = user_query["request"]
        method, endpoint, http_version = http_request.split(" ")
        body = user_query["body"]

        data = None
        if body != "":
            data = json.loads(body)

        local_request, local_response = await test_annotator.asgi_client.request(method=method, url=endpoint, json=data)
        local_responses[user_query["identifier"]] = local_response
        random_delay = random.random() * 1e-3
        await asyncio.sleep(random_delay)

        integration_response = await integration_client.request(
            method=method, url=f"{integration_url}{endpoint}", json=data, timeout=600.0
        )
        integration_responses[user_query["identifier"]] = integration_response
        random_delay = random.random() * 1e-3
        await asyncio.sleep(random_delay)

    unique_identifiers = [user_query["identifier"] for user_query in query_list]
    for unique_identifier in unique_identifiers:
        local_response = local_responses[unique_identifier]
        integration_response = integration_responses[unique_identifier]
        assert local_response.status_code == integration_response.status_code


@pytest.mark.performance
@pytest.mark.parametrize(
    "data_store, num_workers",
    [
        ("cleaned_annotator_logs.json", 4),
        ("cleaned_annotator_logs.json", 8),
        ("cleaned_annotator_logs.json", 16),
    ],
)
def test_multiple_users_querying(
    temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: str, num_workers: int
):
    """
    Similar to the `test_integration_server_responses` test, however we now want to test it a
    multiprocessing flavor to attempt to similar multiple users at once hitting the server
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        query_list = json.load(file_handle)

    for user_query in query_list:
        user_query["identifier"] = str(uuid.uuid4())

    integration_futures = {}
    integration_url = "https://annotator.ci.transltr.io"
    with multiprocessing.Pool(num_workers) as worker_pool:
        for index, user_query in enumerate(query_list):
            http_request = user_query["request"]
            method, endpoint, http_version = http_request.split(" ")
            body = user_query["body"]

            if method == "GET":
                httpcallback = httpx.get
            elif method == "POST":
                httpcallback = httpx.post

            data = None
            if body != "":
                data = body

            worker_request_arguments = {"url": f"{integration_url}{endpoint}", "data": data, "timeout": 600}

            logger.info("Spawning process #%s -> %s", index, worker_request_arguments["url"])
            async_integration_future = worker_pool.apply_async(httpcallback, kwds=worker_request_arguments)

            integration_futures[user_query["identifier"]] = async_integration_future
            random_delay = random.random() * 1e-3
            time.sleep(random_delay)

        unique_identifiers = [user_query["identifier"] for user_query in query_list]
        for unique_identifier in unique_identifiers:
            integration_future = integration_futures[unique_identifier]
            integration_response = integration_future.get()
            response_struct = {
                "uuid": unique_identifier,
                "status": integration_response.status_code,
            }
            logger.info("Recieved response %s", response_struct)


@pytest.mark.performance
@pytest.mark.parametrize(
    "delay",
    [1e-9, 1e-6, 1e-3],
)
def test_bulk_get(temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, delay: float):
    """
    Bulk GET testing to attempt and overload the system to get a gateway error with
    the server instance
    """
    iterations = 1000
    endpoint = "/curie/NCBIGene:1017"
    num_workers = 16

    integration_url = "https://annotator.ci.transltr.io"

    bulk_requests = {}
    for index in range(iterations):
        bulk_requests[str(uuid.uuid4())] = {"url": f"{integration_url}{endpoint}", "timeout": 30}

    integration_futures = {}
    with multiprocessing.Pool(num_workers) as worker_pool:
        for index, (request_uuid, request_args) in enumerate(bulk_requests.items()):
            logger.info("Spawning process #%s -> %s", index, request_args["url"])
            async_integration_future = worker_pool.apply_async(httpx.get, kwds=request_args)

            integration_futures[request_uuid] = async_integration_future
            random_delay = random.random() * delay
            time.sleep(random_delay)

        collector = collections.defaultdict(list)
        for index, request_uuid in enumerate(bulk_requests.keys()):
            integration_future = integration_futures[request_uuid]
            integration_response = integration_future.get()
            collector[integration_response.status_code].append(integration_response)
            logger.info("Recieved response iteration #%s", index)

    assert len(collector[200]) == iterations


@pytest.mark.performance
@pytest.mark.parametrize(
    "data_store, delay, num_workers",
    [
        ("bulk_post.json", 1e-9, 8),
        ("bulk_post.json", 1e-6, 8),
        ("bulk_post.json", 1e-9, 16),
        ("bulk_post.json", 1e-6, 16),
    ],
)
def test_bulk_post(
    temporary_data_storage: Union[str, Path],
    test_annotator: sanic.Sanic,
    data_store: str,
    delay: float,
    num_workers: int,
):
    """
    Bulk POST testing to attempt and overload the system to get a gateway error with
    the server instance
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        bulk_post_query = json.load(file_handle)

    endpoint = bulk_post_query["endpoint"]
    iterations = bulk_post_query["iterations"]
    body = bulk_post_query["body"]

    integration_url = "https://annotator.ci.transltr.io"

    bulk_requests = {}
    for index in range(iterations):
        bulk_requests[str(uuid.uuid4())] = {"data": body, "url": f"{integration_url}{endpoint}", "timeout": 30}

    integration_futures = {}
    with multiprocessing.Pool(num_workers) as worker_pool:
        for index, (request_uuid, request_args) in enumerate(bulk_requests.items()):
            logger.info("Spawning process #%s -> %s", index, request_args["url"])
            async_integration_future = worker_pool.apply_async(httpx.post, kwds=request_args)

            integration_futures[request_uuid] = async_integration_future
            random_delay = random.random() * delay
            time.sleep(random_delay)

        collector = collections.defaultdict(list)
        for index, request_uuid in enumerate(bulk_requests.keys()):
            integration_future = integration_futures[request_uuid]
            integration_response = integration_future.get()
            collector[integration_response.status_code].append(integration_response)
            logger.info("Recieved response iteration #%s", index)

    assert len(collector[200]) == iterations


@pytest.mark.performance
@pytest.mark.parametrize(
    "data_store",
    [
        "ara/ara-aragorn_annotator_nodes.json",
        "ara/ara-bte_annotator_nodes.json",
        "ara/ara-improving_annotator_nodes.json",
        "ara/ara-unsecret_annotator_nodes.json",
    ],
)
def test_ara_integration_trapi_requests(
    temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: str
):
    """
    Similar to the `test_integration_server_responses` test, however we now want to test it a
    multiprocessing flavor to attempt to similar multiple users at once hitting the server
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        ara_request_struct = json.load(file_handle)
        ara_request = json.dumps(ara_request_struct)

    num_workers = random.choice([4, 8, 16])
    integration_futures = []
    integration_url = "https://annotator.ci.transltr.io"
    worker_request_arguments = {"url": f"{integration_url}/trapi/", "data": ara_request}

    with multiprocessing.Pool(num_workers) as worker_pool:
        for worker in range(num_workers):
            integration_future = worker_pool.apply_async(httpx.post, kwds=worker_request_arguments)
            logger.info("Spawning process #%s -> %s", worker, worker_request_arguments["url"])
            integration_futures.append(integration_future)
            random_delay = random.random() * 1e-3
            time.sleep(random_delay)

        for index, ara_future in enumerate(integration_futures):
            logger.info("Waiting on future #%s", index)
            ara_response = ara_future.get()
            assert ara_response.status_code == 200
            logger.info(ara_response.json())
