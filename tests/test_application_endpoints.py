from pathlib import Path
from typing import Dict, List, Union
from unittest.mock import patch
import json

import pytest
import sanic

from biothings_annotator import utils
from biothings_annotator.annotator import Annotator
from biothings_annotator.application.views import VersionView


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/status/"])
def test_status_get(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint GET when the response is HTTP 200
    """
    request, response = test_annotator.test_client.request(endpoint, http_method="get")

    assert request.method == "GET"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    expected_response_body = {"success": True}
    assert isinstance(response.json, dict)
    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"
    assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/status/"])
def test_status_head(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint HEAD when the response is HTTP 200
    """
    request, response = test_annotator.test_client.request(endpoint, http_method="head")

    assert request.method == "HEAD"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert response.json is None
    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/status/"])
def test_status_get_error(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint GET when an Exception is raised
    Mocking the annotate_curie method to raise an exception
    """
    with patch.object(Annotator, "annotate_curie", side_effect=Exception("Simulated error")):
        request, response = test_annotator.test_client.request(endpoint, http_method="get")

        assert request.method == "GET"
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"success": False, "error": "Exception('Simulated error')"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert not response.is_success
        assert response.is_error
        assert response.is_closed
        assert response.status_code == 400
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/status/"])
def test_status_get_failed_data_check(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint GET when the data check fails
    Mocking the annotate_curie method to return a value that doesn't contain "NCBIGene:1017"
    """
    # Mock the return value to simulate the data check failure
    with patch.object(Annotator, "annotate_curie", return_value={"_id": "some_other_id"}):
        request, response = test_annotator.test_client.request(endpoint, http_method="get")

        assert request.method == "GET"
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"success": False, "error": "Service unavailable due to a failed data check!"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert not response.is_success
        assert response.is_error
        assert response.is_closed
        assert response.status_code == 500
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/version/"])
def test_version_get_success(test_annotator: sanic.Sanic, endpoint: str):
    """
    Test the Version endpoint GET method with a successful file read
    """
    with patch.object(VersionView, "open_version_file", return_value="GITHUB_HASH_VERSION_ABC123") as mock_file_read:
        request, response = test_annotator.test_client.request(endpoint, http_method="get")

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"version": "GITHUB_HASH_VERSION_ABC123"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/version/"])
def test_version_get_file_not_found(test_annotator: sanic.Sanic, endpoint: str):
    """
    Test the Version endpoint GET method when version.txt is not found
    """
    with patch.object(VersionView, "open_version_file", side_effect=FileNotFoundError) as mock_file_read:
        request, response = test_annotator.test_client.request(endpoint, http_method="get")

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"version": "Unknown"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/version/"])
def test_version_get_exception(test_annotator: sanic.Sanic, endpoint: str):
    """
    Test the Version endpoint GET method when an exception occurs
    """
    with patch.object(VersionView, "open_version_file", side_effect=Exception("Simulated error")) as mock_file_read:
        request, response = test_annotator.test_client.request(endpoint, http_method="get")

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"version": "Unknown"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.parametrize("data_store", ["expected_curie.json"])
def test_curie_get(temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: Dict):
    """
    Tests the CURIE endpoint GET
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        expected_curie_body = json.load(file_handle)

    endpoint = "/curie/"
    curie_id = "NCBIGene:1017"
    url = f"{endpoint}{curie_id}"
    request, response = test_annotator.test_client.request(url, http_method="get")

    assert request.method == "GET"
    assert request.is_safe
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == url

    response_body = response.json
    response_body[curie_id][0].pop("_score")
    assert response.json == expected_curie_body

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.parametrize(
    "endpoint, batch_curie",
    (
        [
            "/curie/",
            [
                "NCBIGene:695",
                "MONDO:0001222",
                "DOID:6034",
                "CHEMBL.COMPOUND:821",
                "PUBCHEM.COMPOUND:3406",
                "CHEBI:192712",
                "CHEMBL.COMPOUND:3707246",
            ],
        ],
        [
            "/curie/",
            {
                "ids": [
                    "NCBIGene:695",
                    "MONDO:0001222",
                    "DOID:6034",
                    "CHEMBL.COMPOUND:821",
                    "PUBCHEM.COMPOUND:3406",
                    "CHEBI:192712",
                    "CHEMBL.COMPOUND:3707246",
                ]
            },
        ],
    ),
)
def test_curie_post(test_annotator: sanic.Sanic, endpoint: str, batch_curie: Union[List, Dict]):
    """
    Tests the CURIE endpoint POST
    """
    if isinstance(batch_curie, list):
        curie_ids = set(batch_curie)
    elif isinstance(batch_curie, dict):
        curie_ids = set(batch_curie["ids"])

    request, response = test_annotator.test_client.request(endpoint, http_method="post", json=batch_curie)

    assert request.method == "POST"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert isinstance(response.json, dict)
    assert set(response.json.keys()) == curie_ids

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.unit
@pytest.mark.parametrize("data_store", ["trapi_request.json"])
def test_trapi_post(temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: Dict):
    """
    Tests the POST endpoints for our annotation service
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        trapi_body = json.load(file_handle)

    endpoint = "/trapi/"
    request, response = test_annotator.test_client.request(endpoint, http_method="post", json=trapi_body)

    assert request.method == "POST"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"

    node_set = set(trapi_body["message"]["knowledge_graph"]["nodes"].keys())

    annotation = response.json
    assert isinstance(annotation, dict)
    for key, attribute in annotation.items():
        assert key in node_set
        if isinstance(attribute, dict):
            attribute = [attribute]
        assert isinstance(attribute, list)
        for subattribute in attribute:
            assert isinstance(subattribute, dict)
            subattribute_collection = subattribute.get("attributes", None)

            assert isinstance(subattribute_collection, list)
            for subattributes in subattribute_collection:
                assert subattributes["attribute_type_id"] == "biothings_annotations"
                assert isinstance(subattributes["value"], list)
                for values in subattributes["value"]:
                    notfound = values.get("notfound", False)
                    if notfound:
                        curie_prefix, query = utils.parse_curie(key)
                        assert values == {"query": query, "notfound": True}
                    else:
                        assert isinstance(values, dict)
                        query = values.get("query", None)
                        assert query is not None
                        identifier = values.get("_id", None)
                        assert identifier is not None
                        score = values.get("_score", None)
                        assert score is not None


@pytest.mark.unit
@pytest.mark.parametrize("data_store", ["expected_curie.json"])
def test_annotator_get_redirect(
    temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: Dict
):
    """
    Tests the legacy endpoint /annotator with a redirect to the
    /curie/ endpoint
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        expected_curie_body = json.load(file_handle)

    endpoint = "/annotator/"
    curie_id = "NCBIGene:1017"
    url = f"{endpoint}{curie_id}"
    request, response = test_annotator.test_client.request(
        url, http_method="get", follow_redirects=True, allow_redirects=True
    )

    assert request.method == "GET"
    assert request.is_safe
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == url

    response_body = response.json
    response_body[curie_id][0].pop("_score")
    assert response.json == expected_curie_body

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.unit
@pytest.mark.parametrize("data_store", ["trapi_request.json"])
def test_annotator_post_redirect(
    temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: Dict
):
    """
    Tests the annotator redirect for the /trapi/ POST endpoint
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        trapi_body = json.load(file_handle)

    endpoint = "/annotator/"
    request, response = test_annotator.test_client.request(
        endpoint, http_method="post", json=trapi_body, follow_redirects=True, allow_redirects=True
    )

    assert request.method == "POST"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"

    node_set = set(trapi_body["message"]["knowledge_graph"]["nodes"].keys())

    annotation = response.json
    assert isinstance(annotation, dict)
    for key, attribute in annotation.items():
        assert key in node_set
        if isinstance(attribute, dict):
            attribute = [attribute]
        assert isinstance(attribute, list)
        for subattribute in attribute:
            assert isinstance(subattribute, dict)
            subattribute_collection = subattribute.get("attributes", None)

            assert isinstance(subattribute_collection, list)
            for subattributes in subattribute_collection:
                assert subattributes["attribute_type_id"] == "biothings_annotations"
                assert isinstance(subattributes["value"], list)
                for values in subattributes["value"]:
                    notfound = values.get("notfound", False)
                    if notfound:
                        curie_prefix, query = utils.parse_curie(key)
                        assert values == {"query": query, "notfound": True}
                    else:
                        assert isinstance(values, dict)
                        query = values.get("query", None)
                        assert query is not None
                        identifier = values.get("_id", None)
                        assert identifier is not None
                        score = values.get("_score", None)
                        assert score is not None
