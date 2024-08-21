import pytest
import sanic


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


@pytest.mark.parametrize("endpoint", [
    "/curie/troglydte:4883", "/curie/predicate-subject"
])
def test_invalid_curie_handling(test_annotator: sanic.Sanic, endpoint: str):
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

    breakpoint()
    assert response.status == 400

    response_body = response.json
    assert response_body["message"] == "Router was unable to find a valid route"
    assert response_body["exception"] == f"Method GET not allowed for URL {endpoint}" 
