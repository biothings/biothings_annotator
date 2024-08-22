import json
from typing import Union

import pytest
import sanic

from biothings_annotator.annotator.settings import BIOLINK_PREFIX_to_BioThings


@pytest.mark.parametrize("endpoint", ["/curie/", "/trapi/"])
def test_method_not_allowed_handling(test_annotator: sanic.Sanic, endpoint: str):
    """
    Verifies our exception handling for unknown endpoints

    We want to ensure we always have a JSON response for our errors
    due to our service primarily serving as an endpoint to retrieve JSON
    data

    We also want to make sure that our custom exception for overriding the behavior
    works as expected and that it attempts to suggest an appropriate route if it detects
    a similar routing path
    """
    request, response = test_annotator.test_client.request(endpoint, http_method="get")

    assert response.status == 400

    response_body = response.json
    assert response_body["requestpath"] == endpoint
    assert response_body["message"] == "Router was unable to find a valid route"
    assert response_body["exception"] == f"Method GET not allowed for URL {endpoint}"


@pytest.mark.parametrize("endpoint", ["/curie/troglydte:4883", "/curie/predicate-subject"])
def test_invalid_curie_handling(test_annotator: sanic.Sanic, endpoint: str):
    """
    Checks to ensure proper output formatting for the CURIE endpoint. We should
    always gets a JSON response back with some additional debugging information
    about the query
    """
    request, response = test_annotator.test_client.request(endpoint, http_method="get")

    assert response.status == 400

    input_curie = endpoint.split("/")[-1]
    response_body = response.json
    assert response_body["input"] == input_curie

    expected_message = f"Unsupported CURIE id: {input_curie}. "
    if ":" not in input_curie:
        expected_message += "Invalid structure for the provided CURIE id. Expected form <node>:<id>"

    assert response_body["message"] == expected_message
    assert response_body["supported_nodes"] == list(BIOLINK_PREFIX_to_BioThings.keys())


@pytest.mark.parametrize(
    "data",
    [{}, {"message": {"knowledge_graph": {"nodes": []}}}, {"message": {"knowledge_graph": {"node": {"node0": {}}}}}],
)
def test_invalid_trapi_input_handling(test_annotator: sanic.Sanic, data: dict):
    """
    Similar to the input curie processing we want to ensure we provide proper JSON
    response for when the TRAPI input isn't valid
    """
    endpoint = "/trapi/"
    request, response = test_annotator.test_client.request(endpoint, http_method="post", json=data)

    assert response.status == 400
    response_body = response.json
    assert response_body["input"] == data
    assert response_body["endpoint"] == endpoint
    assert response_body["message"] == "Unsupported TRAPI input structure"


@pytest.mark.parametrize(
    "endpoint, batch_curie",
    (
        [
            "/curie/",
            {
                "id": [
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
        ["/curie/", []],
        ["/curie/", {"ids": []}],
    ),
)
def test_invalid_batch_curie(test_annotator: sanic.Sanic, endpoint: str, batch_curie: Union[list, dict]):
    """
    Tests erroneous formed or incorrect JSON bodies sent to the CURIE POST endpoint
    """
    request, response = test_annotator.test_client.request(endpoint, http_method="post", json=batch_curie)

    assert request.method == "POST"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert isinstance(response.json, dict)
    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_closed
    assert response.status_code == 400
    assert response.encoding == "utf-8"

    response_body = response.json
    assert response_body["endpoint"] == endpoint
    assert response_body["input"] == batch_curie

    expected_message = (
        "No CURIE ID's found in request body. "
        "Expected format: {'ids': ['id0', 'id1', ... 'idN']} || ['id0', 'id1', ... 'idN']. "
        f"Received request body: {json.dumps(batch_curie)}"
    )
    assert response_body["message"] == expected_message
