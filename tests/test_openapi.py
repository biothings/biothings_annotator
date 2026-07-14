import json
from pathlib import Path

import pytest


OPENAPI_PATH = Path(__file__).parents[1] / "biothings_annotator" / "webapp" / "openapi.json"
DEFAULT_CONFIG_PATH = (
    Path(__file__).parents[1] / "biothings_annotator" / "application" / "configuration" / "default.json"
)
DEPLOY_CONFIG_PATH = Path(__file__).parents[1] / "docker" / "configuration" / "config.json"
QUERY_OPERATIONS = (
    ("/curie/{curie}", "get"),
    ("/curie", "post"),
    ("/trapi", "post"),
)


@pytest.mark.unit
def test_query_backend_override_is_documented_for_all_query_operations():
    with OPENAPI_PATH.open(encoding="utf-8") as openapi_file:
        specification = json.load(openapi_file)

    query_backend_parameter = specification["components"]["parameters"]["QueryBackend"]
    assert query_backend_parameter["name"] == "query_backend"
    assert query_backend_parameter["in"] == "query"
    assert query_backend_parameter["required"] is False
    assert query_backend_parameter["allowEmptyValue"] is True
    assert query_backend_parameter["schema"] == {"type": "string"}
    assert "Unsupported values are ignored and use the deployment default" in query_backend_parameter[
        "description"
    ]

    for path, method in QUERY_OPERATIONS:
        operation = specification["paths"][path][method]
        assert {"$ref": "#/components/parameters/QueryBackend"} in operation["parameters"]
        assert operation["responses"]["200"]["headers"]["X-Query-Backend"] == {
            "$ref": "#/components/headers/QueryBackend"
        }

    assert "InvalidQueryBackendError" not in json.dumps(specification)


@pytest.mark.unit
@pytest.mark.parametrize("config_path", [DEFAULT_CONFIG_PATH, DEPLOY_CONFIG_PATH])
def test_query_backend_response_header_is_exposed_by_cors(config_path):
    with config_path.open(encoding="utf-8") as config_file:
        configuration = json.load(config_file)

    cors = configuration["application"]["extension"]["cors"]
    assert cors["CORS_EXPOSE_HEADERS"] == "X-Query-Backend"
