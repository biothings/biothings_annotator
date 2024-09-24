"""
Tests the metadata generation and configuration
"""

import sanic
import yaml


def test_metadata_generation(test_annotator: sanic.Sanic):
    """
    Tests the Status endpoint GET when the response is HTTP 200
    """
    endpoint = "/metadata/"
    request, response = test_annotator.test_client.request(endpoint, http_method="get")

    assert response.status_code == 200

    yaml_object = yaml.safe_load(response.text)
    assert isinstance(yaml_object, dict)

    openapi_info = yaml_object.get("info", None)
    assert isinstance(openapi_info, dict)
    openapi_version = yaml_object.get("openapi", None)
    assert isinstance(openapi_version, str)
    application_paths = yaml_object.get("paths", None)
    assert isinstance(application_paths, dict)
