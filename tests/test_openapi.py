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
        assert operation["responses"]["200"]["headers"]["X-Skipped-Curie-Prefixes"] == {
            "$ref": "#/components/headers/SkippedCuriePrefixes"
        }
        assert operation["responses"]["200"]["headers"]["Cache-Control"] == {
            "$ref": "#/components/headers/AnnotationCacheControl"
        }
        assert operation["responses"]["503"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/SourceDiscoveryError"
        }
        assert operation["responses"]["503"]["headers"]["Cache-Control"] == {
            "$ref": "#/components/headers/TransientErrorCacheControl"
        }

    skipped_prefixes_header = specification["components"]["headers"]["SkippedCuriePrefixes"]
    assert skipped_prefixes_header["schema"] == {"type": "string", "example": "PMID"}
    assert "source discovery confirmed" in skipped_prefixes_header["description"]
    assert specification["components"]["headers"]["TransientErrorCacheControl"]["schema"] == {
        "type": "string",
        "enum": ["no-store"],
    }

    skipped_result = specification["components"]["schemas"]["BackendSkipResult"]
    assert skipped_result["type"] == "array"
    assert skipped_result["minItems"] == 1
    skipped_hit = skipped_result["items"]
    assert skipped_hit["required"] == [
        "query",
        "notfound",
        "skipped",
        "reason",
        "source",
        "query_backend",
    ]
    assert skipped_hit["properties"]["notfound"] == {"type": "boolean", "enum": [True]}
    assert skipped_hit["properties"]["skipped"] == {"type": "boolean", "enum": [True]}
    assert skipped_hit["properties"]["reason"]["enum"] == ["source_unavailable_for_backend"]

    discovery_error = specification["components"]["schemas"]["SourceDiscoveryError"]
    assert discovery_error["required"] == ["input", "endpoint", "message", "source"]
    assert discovery_error["properties"]["message"]["enum"] == [
        "Unable to determine BioThings source availability."
    ]

    assert "InvalidQueryBackendError" not in json.dumps(specification)


@pytest.mark.unit
@pytest.mark.parametrize("config_path", [DEFAULT_CONFIG_PATH, DEPLOY_CONFIG_PATH])
def test_cors_configuration_uses_supported_keys(config_path):
    with config_path.open(encoding="utf-8") as config_file:
        configuration = json.load(config_file)

    cors = configuration["application"]["extension"]["cors"]
    exposed_headers = {header.strip() for header in cors["CORS_EXPOSE_HEADERS"].split(",")}
    assert exposed_headers == {"X-Query-Backend", "X-Skipped-Curie-Prefixes"}
    assert cors["CORS_SUPPORTS_CREDENTIALS"] is False
    assert "CORS_SUPPORS_CREDENTIALS" not in cors
