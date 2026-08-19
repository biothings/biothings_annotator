import json
import re
from pathlib import Path

import pytest

from biothings_annotator.application.views.document_metadata import (
    DocumentMetadataRequestError,
    validate_publication_ids,
)


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
def test_all_document_metadata_fast_paths_are_documented():
    with OPENAPI_PATH.open(encoding="utf-8") as openapi_file:
        specification = json.load(openapi_file)

    publication_paths = specification["paths"]
    assert set(publication_paths["/publications"]) == {"get", "post"}
    assert set(publication_paths["/publications/{publication_id}"]) == {"get"}

    legacy_get = publication_paths["/publications"]["get"]
    publication_get = publication_paths["/publications/{publication_id}"]["get"]
    publication_post = publication_paths["/publications"]["post"]

    assert legacy_get["operationId"] == "get~legacy_document_metadata_endpoint"
    pubids_parameter = next(parameter for parameter in legacy_get["parameters"] if parameter.get("name") == "pubids")
    assert pubids_parameter["in"] == "query"
    assert pubids_parameter["required"] is True
    assert pubids_parameter["style"] == "form"
    assert pubids_parameter["explode"] is False
    assert pubids_parameter["schema"] == {"$ref": "#/components/schemas/PublicationIdList"}

    assert publication_get["operationId"] == "get~document_metadata_endpoint"
    publication_id_parameter = next(
        parameter for parameter in publication_get["parameters"] if parameter.get("name") == "publication_id"
    )
    assert publication_id_parameter["in"] == "path"
    assert publication_id_parameter["required"] is True
    assert publication_id_parameter["schema"] == {"$ref": "#/components/schemas/PublicationId"}

    assert publication_post["operationId"] == "post~batch_document_metadata_endpoint"
    assert publication_post["requestBody"]["required"] is True
    post_json = publication_post["requestBody"]["content"]["application/json"]
    assert post_json["schema"] == {"$ref": "#/components/schemas/DocumentMetadataRequest"}
    assert set(post_json["examples"]) == {"object", "array"}

    request_id_reference = {"$ref": "#/components/parameters/DocumentMetadataRequestId"}
    for operation in (legacy_get, publication_get, publication_post):
        assert "multi-get" in operation["description"]
        assert request_id_reference in operation["parameters"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/DocumentMetadataResponse"
        }
        assert set(operation["responses"]) == {"200", "400", "500"}

    publication_id_schema = specification["components"]["schemas"]["PublicationId"]
    documented_pattern = re.compile(publication_id_schema["pattern"])
    for accepted in ("PMID:30690000", "PMC:PMC1904490", "doi:10.1242/jcs.03153", "DOI:10.1242/JCS.03153"):
        assert documented_pattern.fullmatch(accepted), accepted
    for rejected in ("PMID:0", "PMC:12345", "doi:notadoi", "CHEBI:15377"):
        assert not documented_pattern.fullmatch(rejected), rejected


@pytest.mark.unit
def test_documented_publication_id_pattern_matches_the_served_validation():
    """A client validating against the spec must not reject IDs the service accepts."""
    with OPENAPI_PATH.open(encoding="utf-8") as openapi_file:
        specification = json.load(openapi_file)

    documented_pattern = re.compile(specification["components"]["schemas"]["PublicationId"]["pattern"])
    candidates = (
        "PMID:30690000",
        "pmid:30690000",
        "PMID:0",
        "PMID:not-a-number",
        "PMC:PMC1904490",
        "pmc:pmc1904490",
        "PMC:12345",
        "doi:10.1242/jcs.03153",
        "DOI:10.1242/JCS.03153",
        "doi:notadoi",
        "CHEBI:15377",
        # Non-ASCII decimal digits. The documented pattern is ASCII-only, so the
        # served regex must not use \d, which would accept these and then never
        # match the ASCII identifiers stored in the index.
        "PMID:1\u0662",
        "PMC:PMC\u0661",
        "doi:10.\u0661/x",
    )

    for candidate in candidates:
        try:
            validate_publication_ids([candidate])
        except DocumentMetadataRequestError:
            served = False
        else:
            served = True
        assert bool(documented_pattern.fullmatch(candidate)) is served, candidate

    publication_id_list = specification["components"]["schemas"]["PublicationIdList"]
    assert publication_id_list["minItems"] == 1
    assert publication_id_list["maxItems"] == 100
    assert publication_id_list["items"] == {"$ref": "#/components/schemas/PublicationId"}

    request_schema = specification["components"]["schemas"]["DocumentMetadataRequest"]
    assert request_schema["oneOf"][0] == {"$ref": "#/components/schemas/PublicationIdList"}
    object_request = request_schema["oneOf"][1]
    assert object_request["required"] == ["ids"]
    assert object_request["properties"]["ids"] == {"$ref": "#/components/schemas/PublicationIdList"}
    assert object_request["properties"]["request_id"]["type"] == "string"

    request_id_parameter = specification["components"]["parameters"]["DocumentMetadataRequestId"]
    assert request_id_parameter["name"] == "request_id"
    assert request_id_parameter["in"] == "query"
    assert request_id_parameter["required"] is False

    response_schema = specification["components"]["schemas"]["DocumentMetadataResponse"]
    assert response_schema["required"] == ["_meta", "results", "not_found"]
    assert response_schema["properties"]["results"]["additionalProperties"] == {
        "$ref": "#/components/schemas/PublicationMetadata"
    }


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
