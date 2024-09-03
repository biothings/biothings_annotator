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
import json
import logging
import multiprocessing
import random
import sqlite3
import string
import time
import uuid

import httpx
import pytest
import requests
import sanic


logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("data_store", ["cleaned_annotator_logs.json"])
async def test_integration_server_responses(
    temporary_data_storage: Union[str, Path],
    test_annotator: sanic.Sanic,
    performance_database: sqlite3.Connection,
    data_store: str,
    request,
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

    test_table = request.node.originalname + "_" + "".join(random.choice(string.ascii_lowercase) for i in range(16))
    table_command = (
        f"CREATE TABLE {test_table} "
        "(endpoint, method, body, local_response, local_status, integration_response, integration_status)"
    )
    performance_database.execute(table_command)

    for user_query in query_list:
        user_query["identifier"] = str(uuid.uuid4())

    local_responses = {}
    integration_responses = {}
    integration_client = httpx.AsyncClient()
    integration_url = "https://annotator.ci.transltr.io"

    with performance_database as connection:
        for user_query in query_list:
            http_request = user_query["request"]
            method, endpoint, http_version = http_request.split(" ")
            body = user_query["body"]

            data = None
            if body != "":
                data = json.loads(body)

            local_request, local_response = await test_annotator.asgi_client.request(
                method=method, url=endpoint, json=data
            )
            local_responses[user_query["identifier"]] = local_response
            random_delay = random.random() * 1e-3
            await asyncio.sleep(random_delay)

            integration_response = await integration_client.request(
                method=method, url=f"{integration_url}{endpoint}", json=data, timeout=600.0
            )
            integration_responses[user_query["identifier"]] = integration_response
            random_delay = random.random() * 1e-3
            await asyncio.sleep(random_delay)

            insertion_data = {
                "endpoint": endpoint,
                "method": method,
                "body": body,
                "local_response": local_response.content,
                "local_status": local_response.status_code,
                "integration_response": integration_response.content,
                "integration_status": integration_response.status_code,
            }
            connection.execute(
                f"INSERT INTO {test_table} VALUES(:endpoint, :method, :body, :local_response, :local_status, :integration_response, :integration_status)",
                insertion_data,
            )

    unique_identifiers = [user_query["identifier"] for user_query in query_list]
    for unique_identifier in unique_identifiers:
        local_response = local_responses[unique_identifier]
        integration_response = integration_responses[unique_identifier]
        assert local_response.status_code == integration_response.status_code


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
                httpcallback = requests.get
            elif method == "POST":
                httpcallback = requests.post

            data = None
            if body != "":
                data = json.loads(body)

            worker_request_arguments = {"url": f"{integration_url}{endpoint}", "data": data}

            logger.info("Spawning process #%s -> %s", index, worker_request_arguments["url"])
            async_integration_future = worker_pool.apply_async(httpcallback, kwds=worker_request_arguments)

            integration_futures[user_query["identifier"]] = async_integration_future
            random_delay = random.random() * 1e-3
            time.sleep(random_delay)

        unique_identifiers = [user_query["identifier"] for user_query in query_list]
        for unique_identifier in unique_identifiers:
            integration_future = integration_futures[unique_identifier]
            integration_response = integration_future.get()
            logger.info("Recieved response %s", unique_identifier)


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
        ara_request = json.load(file_handle)

    num_workers = random.choice([4, 8, 16])
    integration_futures = []
    integration_url = "https://annotator.ci.transltr.io"
    worker_request_arguments = {"url": f"{integration_url}/trapi/", "data": ara_request}

    with multiprocessing.Pool(num_workers) as worker_pool:
        for worker in range(num_workers):
            breakpoint()
            integration_future = worker_pool.apply_async(requests.post, kwds=worker_request_arguments)
            logger.info("Spawning process #%s -> %s", worker, worker_request_arguments["url"])
            integration_futures.append(integration_future)
            random_delay = random.random() * 1e-3
            time.sleep(random_delay)

        for index, ara_future in enumerate(integration_futures):
            logger.info("Waiting on future #%s", index)
            ara_response = ara_future.get()
            assert ara_response.status_code == 200
