import asyncio
import json
from pathlib import Path
from typing import Dict, List, Union
from unittest.mock import AsyncMock, patch

import pytest
import sanic

from biothings_annotator import utils
from biothings_annotator.annotator import Annotator
from biothings_annotator.annotator.settings import QUERY_BACKEND_ENV
from biothings_annotator.application.views import VersionView


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/status/"])
async def test_status_get(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint GET when the response is HTTP 200
    """
    with patch.object(Annotator, "annotate_curie", return_value={"NCBIGene:1017": [{"_id": "1017"}]}) as mock_annotate:
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

        mock_annotate.assert_awaited_once_with(
            "NCBIGene:1017",
            fields="_id",
            raw=True,
            include_extra=False,
        )

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
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/status/"])
async def test_status_head(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint HEAD when the response is HTTP 200
    """
    with patch.object(Annotator, "annotate_curie", return_value={"NCBIGene:1017": [{"_id": "1017"}]}) as mock_annotate:
        request, response = await test_annotator.asgi_client.request(method="head", url=endpoint)

        mock_annotate.assert_awaited_once_with(
            "NCBIGene:1017",
            fields="_id",
            raw=True,
            include_extra=False,
        )

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
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/status/"])
async def test_status_get_error(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint GET when an Exception is raised
    Mocking the annotate_curie method to raise an exception
    """
    with patch.object(Annotator, "annotate_curie", side_effect=Exception("Simulated error")):
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

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
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/status/"])
async def test_status_get_failed_data_check(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the Status endpoint GET when the data check fails
    Mocking the annotate_curie method to return a value that doesn't contain "NCBIGene:1017"
    """
    endpoint = "/status/"

    # Mock the return value to simulate the data check failure
    with patch.object(Annotator, "annotate_curie", return_value={"_id": "some_other_id"}):
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

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
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/version/"])
async def test_version_get_success(test_annotator: sanic.Sanic, endpoint: str, monkeypatch):
    """
    Test the Version endpoint GET method with a successful file read
    """
    monkeypatch.delenv(QUERY_BACKEND_ENV, raising=False)
    monkeypatch.delenv("ELASTICSEARCH_CONNECTION", raising=False)

    with patch.object(VersionView, "open_version_file", return_value="GITHUB_HASH_VERSION_ABC123") as mock_file_read:
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"version": "GITHUB_HASH_VERSION_ABC123", "query_backend": "biothings"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/version/"])
async def test_version_get_reports_elasticsearch_backend(test_annotator: sanic.Sanic, endpoint: str, monkeypatch):
    """
    Test the Version endpoint GET method includes runtime backend metadata.
    """
    monkeypatch.setenv(QUERY_BACKEND_ENV, "elasticsearch")
    monkeypatch.setenv("ELASTICSEARCH_CONNECTION", "ci")

    with patch.object(VersionView, "open_version_file", return_value="GITHUB_HASH_VERSION_ABC123") as mock_file_read:
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {
            "version": "GITHUB_HASH_VERSION_ABC123",
            "query_backend": "elasticsearch",
            "elasticsearch_connection": "ci",
        }
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/version/"])
async def test_version_get_file_not_found(test_annotator: sanic.Sanic, endpoint: str, monkeypatch):
    """
    Test the Version endpoint GET method when version.txt is not found
    """
    monkeypatch.delenv(QUERY_BACKEND_ENV, raising=False)
    monkeypatch.delenv("ELASTICSEARCH_CONNECTION", raising=False)

    with patch.object(VersionView, "open_version_file", side_effect=FileNotFoundError) as mock_file_read:
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"version": "Unknown", "query_backend": "biothings"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/version/"])
async def test_version_get_exception(test_annotator: sanic.Sanic, endpoint: str, monkeypatch):
    """
    Test the Version endpoint GET method when an exception occurs
    """
    monkeypatch.delenv(QUERY_BACKEND_ENV, raising=False)
    monkeypatch.delenv("ELASTICSEARCH_CONNECTION", raising=False)

    with patch.object(VersionView, "open_version_file", side_effect=Exception("Simulated error")) as mock_file_read:
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

        mock_file_read.assert_called_once()

        assert request.method == "GET"
        assert response.status_code == 200
        assert request.query_string == ""
        assert request.scheme == "http"
        assert request.server_path == endpoint

        expected_response_body = {"version": "Unknown", "query_backend": "biothings"}
        assert response.http_version == "HTTP/1.1"
        assert response.content_type == "application/json"
        assert response.is_success
        assert not response.is_error
        assert response.is_closed
        assert response.status_code == 200
        assert response.encoding == "utf-8"
        assert response.json == expected_response_body


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("endpoint", ["/version/"])
async def test_version_get_outer_exception_keeps_cache_header(
    test_annotator: sanic.Sanic, endpoint: str, monkeypatch
):
    """
    Test the Version endpoint preserves default headers on the outer fallback path.
    """
    monkeypatch.delenv(QUERY_BACKEND_ENV, raising=False)
    monkeypatch.delenv("ELASTICSEARCH_CONNECTION", raising=False)

    with patch.object(
        VersionView,
        "build_response_body",
        side_effect=[
            Exception("Simulated response error"),
            {"version": "Unknown", "query_backend": "biothings"},
        ],
    ) as mock_build_response_body:
        request, response = await test_annotator.asgi_client.request(method="get", url=endpoint)

        assert mock_build_response_body.call_count == 2

        assert request.method == "GET"
        assert response.status_code == 200
        expected_cache_control = f"max-age={test_annotator.config.CACHE_MAX_AGE}, public"
        assert response.headers["Cache-Control"] == expected_cache_control
        assert response.json == {"version": "Unknown", "query_backend": "biothings"}


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("data_store", ["expected_curie.json"])
async def test_curie_get(temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: Dict):
    """
    Tests the CURIE endpoint GET
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        expected_curie_body = json.load(file_handle)

    endpoint = "/curie/"
    curie_id = "NCBIGene:1017"
    url = f"{endpoint}{curie_id}"
    request, response = await test_annotator.asgi_client.request(method="get", url=url)

    assert request.method == "GET"
    assert request.is_safe
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == url

    response_body = response.json
    response_body[curie_id][0].pop("_score")

    assert response.json.keys() == expected_curie_body.keys()
    response_curie_annotation = response.json.get(curie_id)
    expected_curie_annotation = expected_curie_body.get(curie_id)

    # Expected length of 1 response for one anootation
    assert len(response_curie_annotation) == len(expected_curie_annotation)

    # Verify structure without the content to avoid having to capture drifting changes
    # in the responses over time. The structure should be more static
    # ['query', 'HGNC', 'MIM', '_id', 'alias', 'go', 'interpro', 'name', 'pharos', 'summary', 'symbol', 'taxid', 'type_of_gene']
    assert response_curie_annotation[0].keys() == expected_curie_annotation[0].keys()

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "encoded_curie,decoded_curie",
    [("NCBIGene%3A1017", "NCBIGene:1017"), ("UniProtKB%3AA0A087WZL8", "UniProtKB:A0A087WZL8")],
)
async def test_curie_decode_parsing(test_annotator: sanic.Sanic, encoded_curie: str, decoded_curie: str):
    """
    Due to the swagger API frontend, we have to ensure that our GET endpoint
    can properly decode the reserved character `:`

    See the following reference for more information on reserved characters:
    https://www.rfc-editor.org/rfc/rfc1738
    """
    endpoint = "/curie/"
    url = f"{endpoint}{encoded_curie}"
    request, response = await test_annotator.asgi_client.request(method="get", url=url)

    assert request.method == "GET"
    assert request.is_safe
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == url

    assert response.json[decoded_curie]

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
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
async def test_curie_post(test_annotator: sanic.Sanic, endpoint: str, batch_curie: Union[List, Dict]):
    """
    Tests the CURIE endpoint POST
    """
    curie_ids = None
    if isinstance(batch_curie, list):
        curie_ids = set(batch_curie)
    elif isinstance(batch_curie, dict):
        curie_ids = set(batch_curie["ids"])

    request, response = await test_annotator.asgi_client.request(method="post", url=endpoint, json=batch_curie)

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
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("data_store", ["trapi_request.json"])
async def test_trapi_post(temporary_data_storage: Union[str, Path], test_annotator: sanic.Sanic, data_store: Dict):
    """
    Tests the POST endpoints for our annotation service
    """
    data_file_path = temporary_data_storage.joinpath(data_store)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        trapi_body = json.load(file_handle)

    endpoint = "/trapi/"
    request, response = await test_annotator.asgi_client.request(method="post", url=endpoint, json=trapi_body)

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
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "method,url,json_body,annotator_patch,annotation_method,expected_args,expected_kwargs",
    [
        (
            "get",
            "/curie/NCBIGene:1017?query_backend=biothings",
            None,
            "biothings_annotator.application.views.curie.Annotator",
            "annotate_curie",
            ("NCBIGene:1017",),
            {"fields": None, "raw": False, "include_extra": True},
        ),
        (
            "post",
            "/curie/?query_backend=biothings",
            ["NCBIGene:1017"],
            "biothings_annotator.application.views.curie.Annotator",
            "annotate_curie_list",
            (),
            {
                "curie_list": ["NCBIGene:1017"],
                "fields": None,
                "raw": False,
                "include_extra": True,
            },
        ),
        (
            "post",
            "/trapi/?query_backend=biothings",
            {"message": {"knowledge_graph": {"nodes": {}}}},
            "biothings_annotator.application.views.trapi.Annotator",
            "annotate_trapi",
            ({"message": {"knowledge_graph": {"nodes": {}}}},),
            {"fields": None, "raw": False, "append": False, "limit": 0, "include_extra": True},
        ),
    ],
)
async def test_query_backend_override_is_forwarded(
    test_annotator: sanic.Sanic,
    method: str,
    url: str,
    json_body,
    annotator_patch: str,
    annotation_method: str,
    expected_args: tuple,
    expected_kwargs: dict,
):
    with patch(annotator_patch) as mock_annotator_class:
        mock_annotator = mock_annotator_class.return_value
        mock_annotator.query_backend = "biothings"
        mock_annotation = AsyncMock(return_value={"result": "ok"})
        setattr(mock_annotator, annotation_method, mock_annotation)

        request_kwargs = {"method": method, "url": url}
        if json_body is not None:
            request_kwargs["json"] = json_body
        _, response = await test_annotator.asgi_client.request(**request_kwargs)

    mock_annotator_class.assert_called_once_with(query_backend="biothings")
    mock_annotation.assert_awaited_once_with(*expected_args, **expected_kwargs)
    assert response.status_code == 200
    assert response.headers["X-Query-Backend"] == "biothings"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_query_backend_omission_uses_deployment_default(test_annotator: sanic.Sanic, monkeypatch):
    monkeypatch.setenv(QUERY_BACKEND_ENV, "elasticsearch")
    mock_annotation = AsyncMock(return_value={"result": "ok"})

    with patch.object(Annotator, "annotate_curie", mock_annotation), patch(
        "biothings_annotator.application.views.curie.Annotator", wraps=Annotator
    ) as mock_annotator_class:
        _, response = await test_annotator.asgi_client.request(method="get", url="/curie/NCBIGene:1017")

    mock_annotator_class.assert_called_once_with(query_backend=None)
    mock_annotation.assert_awaited_once()
    assert response.status_code == 200
    assert response.headers["X-Query-Backend"] == "elasticsearch"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("query_backend", ["elasticsearch", "es"])
async def test_elasticsearch_query_backend_returns_canonical_header(test_annotator: sanic.Sanic, query_backend: str):
    mock_annotation = AsyncMock(return_value={"result": "ok"})

    with patch.object(Annotator, "annotate_curie", mock_annotation), patch(
        "biothings_annotator.application.views.curie.Annotator", wraps=Annotator
    ) as mock_annotator_class:
        _, response = await test_annotator.asgi_client.request(
            method="get", url=f"/curie/NCBIGene:1017?query_backend={query_backend}"
        )

    mock_annotator_class.assert_called_once_with(query_backend=query_backend)
    mock_annotation.assert_awaited_once()
    assert response.status_code == 200
    assert response.headers["X-Query-Backend"] == "elasticsearch"


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("deployment_backend", ["biothings", "elasticsearch"])
@pytest.mark.parametrize(
    "encoded_override,constructor_value",
    [
        ("unsupported", "unsupported"),
        ("", None),
        ("%20%20", "  "),
    ],
)
@pytest.mark.parametrize(
    "method,base_url,json_body,annotator_patch,annotation_method,expected_args,expected_kwargs",
    [
        (
            "get",
            "/curie/NCBIGene:1017",
            None,
            "biothings_annotator.application.views.curie.Annotator",
            "annotate_curie",
            ("NCBIGene:1017",),
            {"fields": None, "raw": False, "include_extra": True},
        ),
        (
            "post",
            "/curie/",
            ["NCBIGene:1017"],
            "biothings_annotator.application.views.curie.Annotator",
            "annotate_curie_list",
            (),
            {
                "curie_list": ["NCBIGene:1017"],
                "fields": None,
                "raw": False,
                "include_extra": True,
            },
        ),
        (
            "post",
            "/trapi/",
            {"message": {"knowledge_graph": {"nodes": {}}}},
            "biothings_annotator.application.views.trapi.Annotator",
            "annotate_trapi",
            ({"message": {"knowledge_graph": {"nodes": {}}}},),
            {"fields": None, "raw": False, "append": False, "limit": 0, "include_extra": True},
        ),
    ],
)
async def test_invalid_query_backend_uses_deployment_default(
    test_annotator: sanic.Sanic,
    monkeypatch,
    deployment_backend: str,
    encoded_override: str,
    constructor_value,
    method: str,
    base_url: str,
    json_body,
    annotator_patch: str,
    annotation_method: str,
    expected_args: tuple,
    expected_kwargs: dict,
):
    monkeypatch.setenv(QUERY_BACKEND_ENV, deployment_backend)
    mock_annotation = AsyncMock(return_value={"result": "ok"})
    request_kwargs = {"method": method, "url": f"{base_url}?query_backend={encoded_override}"}
    if json_body is not None:
        request_kwargs["json"] = json_body

    with patch.object(Annotator, annotation_method, mock_annotation), patch(
        annotator_patch, wraps=Annotator
    ) as mock_annotator_class:
        _, response = await test_annotator.asgi_client.request(**request_kwargs)

    mock_annotator_class.assert_called_once_with(query_backend=constructor_value)
    mock_annotation.assert_awaited_once_with(*expected_args, **expected_kwargs)
    assert response.status_code == 200
    assert response.json == {"result": "ok"}
    assert response.headers["X-Query-Backend"] == deployment_backend


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "method,url,json_body,annotation_method,endpoint",
    [
        ("get", "/curie/NCBIGene:1017", None, "annotate_curie", "/curie/"),
        ("post", "/curie/", ["NCBIGene:1017"], "annotate_curie_list", "/curie/"),
        (
            "post",
            "/trapi/",
            {"message": {"knowledge_graph": {"nodes": {}}}},
            "annotate_trapi",
            "/trapi/",
        ),
    ],
)
async def test_invalid_deployment_query_backend_returns_sanitized_500(
    test_annotator: sanic.Sanic,
    monkeypatch,
    method: str,
    url: str,
    json_body,
    annotation_method: str,
    endpoint: str,
):
    invalid_deployment_value = "invalid-deployment-backend-do-not-expose"
    monkeypatch.setenv(QUERY_BACKEND_ENV, invalid_deployment_value)
    mock_annotation = AsyncMock()
    request_kwargs = {"method": method, "url": url}
    if json_body is not None:
        request_kwargs["json"] = json_body

    with patch.object(Annotator, annotation_method, mock_annotation):
        _, response = await test_annotator.asgi_client.request(**request_kwargs)

    assert response.status_code == 500
    assert response.json == {
        "endpoint": endpoint,
        "message": "Server query backend configuration is invalid.",
    }
    assert invalid_deployment_value not in response.body.decode("utf-8")
    assert "X-Query-Backend" not in response.headers
    mock_annotation.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_query_backend_header_is_cors_exposed(test_annotator: sanic.Sanic):
    mock_annotation = AsyncMock(return_value={"result": "ok"})

    with patch.object(Annotator, "annotate_curie", mock_annotation):
        _, response = await test_annotator.asgi_client.request(
            method="get",
            url="/curie/NCBIGene:1017?query_backend=biothings",
            headers={"Origin": "https://frontend.example"},
        )

    exposed_headers = {
        header.strip().lower() for header in response.headers["Access-Control-Expose-Headers"].split(",")
    }
    assert response.status_code == 200
    assert response.headers["X-Query-Backend"] == "biothings"
    assert "x-query-backend" in exposed_headers


@pytest.mark.unit
@pytest.mark.asyncio(loop_scope="module")
async def test_concurrent_query_backend_overrides_are_request_local(test_annotator: sanic.Sanic, monkeypatch):
    monkeypatch.setenv(QUERY_BACKEND_ENV, "biothings")

    async def annotation_with_backend(annotator, *args, **kwargs):
        selected_backend = annotator.query_backend
        await asyncio.sleep(0)
        return {"backend": selected_backend}

    with patch.object(Annotator, "annotate_curie", new=annotation_with_backend):
        biothings_result, elasticsearch_result = await asyncio.gather(
            test_annotator.asgi_client.request(
                method="get", url="/curie/NCBIGene:1017?query_backend=biothings"
            ),
            test_annotator.asgi_client.request(method="get", url="/curie/NCBIGene:1017?query_backend=es"),
        )

    _, biothings_response = biothings_result
    _, elasticsearch_response = elasticsearch_result
    assert biothings_response.json == {"backend": "biothings"}
    assert biothings_response.headers["X-Query-Backend"] == "biothings"
    assert elasticsearch_response.json == {"backend": "elasticsearch"}
    assert elasticsearch_response.headers["X-Query-Backend"] == "elasticsearch"
