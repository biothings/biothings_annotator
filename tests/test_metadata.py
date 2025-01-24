"""
Tests the metadata generation and configuration
"""

import pytest
import sanic
import yaml


@pytest.mark.unit
@pytest.mark.asyncio(scope="module")
async def test_metadata_generation(test_annotator: sanic.Sanic):
    """
    Tests the metadata endpoint for generating the openapi spec
    """
    endpoint = "/metadata/openapi"
    request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

    assert response.status_code == 200

    yaml_object = yaml.safe_load(response.text)
    assert isinstance(yaml_object, dict)

    openapi_info = yaml_object.get("info", None)
    assert isinstance(openapi_info, dict)
    openapi_version = yaml_object.get("openapi", None)
    assert isinstance(openapi_version, str)
    application_paths = yaml_object.get("paths", None)
    assert isinstance(application_paths, dict)
