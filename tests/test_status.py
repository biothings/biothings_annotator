"""Status metadata follows deployment configuration and the served OpenAPI spec."""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sanic import Sanic

from biothings_annotator.application import build_application
from biothings_annotator.application import status_metadata
from biothings_annotator.application.cli.arguments import load_configuration
from biothings_annotator.application.views import status
from biothings_annotator.annotator import Annotator


pytestmark = pytest.mark.unit


@pytest.fixture
def application_configuration(monkeypatch):
    # Each startup check builds an app with the production name without replacing
    # the module-scoped application used by other endpoint tests.
    monkeypatch.setattr(Sanic, "_app_registry", {})
    monkeypatch.delenv("ANNOTATOR_DEPLOYMENT_ENV", raising=False)
    return load_configuration()


@pytest.mark.parametrize("environment", [None, "", "   "])
def test_deployment_environment_defaults_to_unknown(application_configuration, monkeypatch, environment):
    application_configuration["application"]["configuration"].pop("DEPLOYMENT_ENVIRONMENT")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("SERVICE_PROVIDER_API_HOST", "https://biothings.ci.transltr.io")
    if environment is not None:
        monkeypatch.setenv("ANNOTATOR_DEPLOYMENT_ENV", environment)

    application = build_application(application_configuration)

    assert application.config.DEPLOYMENT_ENVIRONMENT == "unknown"


@pytest.mark.parametrize(
    "configured,environment,expected",
    [
        ("ci", None, "ci"),
        (" test ", None, "test"),
        ("ci", "test", "test"),
        ("ci", " prod ", "prod"),
        ("ci", "", "ci"),
        ("ci", "   ", "unknown"),
        ("", None, "unknown"),
        ("   ", None, "unknown"),
    ],
)
def test_deployment_environment_configuration(
    application_configuration, monkeypatch, configured, environment, expected
):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = configured
    if environment is not None:
        monkeypatch.setenv("ANNOTATOR_DEPLOYMENT_ENV", environment)

    application = build_application(application_configuration)
    monkeypatch.setenv("ANNOTATOR_DEPLOYMENT_ENV", "changed-after-startup")

    assert application.config.DEPLOYMENT_ENVIRONMENT == expected


@pytest.mark.parametrize("configured", [None, 1, False, [], {}])
def test_deployment_environment_rejects_nonstring_configuration(application_configuration, configured):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = configured

    with pytest.raises(ValueError, match="DEPLOYMENT_ENVIRONMENT must be a string"):
        build_application(application_configuration)

    assert not Sanic._app_registry


@pytest.mark.parametrize("use_docker_webapp", [False, True])
def test_status_version_uses_served_openapi(monkeypatch, tmp_path, use_docker_webapp):
    bundled_directory = tmp_path / "bundled"
    bundled_directory.mkdir()
    bundled_directory.joinpath("openapi.json").write_text(
        json.dumps({"info": {"version": "2.0-bundled"}}), encoding="utf-8"
    )
    docker_directory = tmp_path / "webapp"
    if use_docker_webapp:
        docker_directory.mkdir()
        docker_directory.joinpath("openapi.json").write_text(
            json.dumps({"info": {"version": "3.0-docker"}}), encoding="utf-8"
        )
    monkeypatch.setattr(status, "WEB_APP_DIRECTORY", bundled_directory)
    monkeypatch.setattr(status, "DOCKER_WEB_APP_DIRECTORY", docker_directory)
    monkeypatch.chdir(tmp_path)
    status.get_openapi_version.cache_clear()
    try:
        assert status.get_openapi_version() == ("3.0-docker" if use_docker_webapp else "2.0-bundled")
    finally:
        status.get_openapi_version.cache_clear()


@pytest.mark.asyncio
async def test_metadata_refresh_is_shared_and_survives_caller_cancellation(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def collect(*args):
        started.set()
        await release.wait()
        return {"biothings": {"sources": {}}, "elasticsearch": {"sources": {}}}

    collector = AsyncMock(side_effect=collect)
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    cache = status_metadata.BackendMetadataCache("https://example.test", "local")
    first = asyncio.create_task(cache.get())
    second = asyncio.create_task(cache.get())
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    result = await second

    assert await cache.get() == result
    collector.assert_awaited_once_with("https://example.test", "local")
    assert set(result) == {"biothings-api", "elasticsearch"}
    assert datetime.fromisoformat(result["biothings-api"]["checked_at"]).tzinfo is not None


@pytest.mark.asyncio
async def test_metadata_requests_reuse_snapshot_until_background_refresh(monkeypatch):
    failed = {"biothings": {"sources": {"mygene": {"error": {"code": "timeout"}}}}}
    recovered = {"biothings": {"sources": {"mygene": {"build_version": "new"}}}}
    collector = AsyncMock(side_effect=[failed, recovered])
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    cache = status_metadata.BackendMetadataCache("https://example.test", "local")

    assert (await cache.get())["biothings-api"]["sources"] == failed["biothings"]["sources"]
    assert (await cache.get())["biothings-api"]["sources"] == failed["biothings"]["sources"]
    assert collector.await_count == 1

    await cache.refresh()
    assert (await cache.get())["biothings-api"]["sources"] == recovered["biothings"]["sources"]
    assert collector.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setting,new_value", [("api_host", "https://other.test"), ("elasticsearch_connection", "test_forward")]
)
async def test_metadata_cache_is_scoped_to_application_and_backend_configuration(monkeypatch, setting, new_value):
    collector = AsyncMock(return_value={"biothings": {"sources": {}}, "elasticsearch": {"sources": {}}})
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    application = SimpleNamespace(ctx=SimpleNamespace())
    annotator = SimpleNamespace(api_host="https://example.test", elasticsearch_connection="local")

    await status_metadata.get_backend_metadata(application, annotator)
    await status_metadata.get_backend_metadata(application, annotator)
    assert collector.await_count == 1
    setattr(annotator, setting, new_value)
    await status_metadata.get_backend_metadata(application, annotator)
    collector.assert_awaited_with(annotator.api_host, annotator.elasticsearch_connection)
    assert collector.await_count == 2

    await status_metadata.get_backend_metadata(SimpleNamespace(ctx=SimpleNamespace()), annotator)
    assert collector.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connection,environment,expected",
    [
        ("ci_forward", "local", "ci_cluster_forwarded"),
        ("test_forward", "local", "test_cluster_forwarded"),
        ("prod_forward", "local", "prod_cluster_forwarded"),
        ("ci_forward", "prod", "ci_cluster_forwarded"),
        ("in_cluster", "ci", "ci_cluster"),
        ("in_cluster", "test", "test_cluster"),
        ("in_cluster", "prod", "prod_cluster"),
        ("in_cluster", "unknown", "unknown_cluster"),
        ("in_cluster", "local", "unknown_cluster"),
        ("local", "prod", "local"),
    ],
)
async def test_status_connection_describes_the_configured_cluster(
    application_configuration, monkeypatch, connection, environment, expected
):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = environment
    application = build_application(application_configuration)
    monkeypatch.setenv("ELASTICSEARCH_CONNECTION", connection)
    # An unavailable backend retains its target label without claiming connectivity.
    collected = {
        "biothings": {"sources": {}},
        "elasticsearch": {
            "connection": connection,
            "sources": {"mygene": {"error": {"code": "connection_error"}}},
        },
    }
    collector = AsyncMock(return_value=collected)
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    with patch.object(Annotator, "annotate_curie", new=AsyncMock(return_value={"NCBIGene:1017": []})):
        _, response = await application.asgi_client.get("/status", headers={"Host": "annotator.test.transltr.io"})

    assert response.status_code == 200
    assert response.json["deployment_environment"] == environment
    elasticsearch = response.json["available_query_backends"]["elasticsearch"]
    assert elasticsearch["connection"] == expected
    assert elasticsearch["sources"]["mygene"]["error"]["code"] == "connection_error"
    assert collected["elasticsearch"]["connection"] == connection


def test_connection_label_uses_forwarded_target_metadata_independently_of_preset_name(monkeypatch):
    monkeypatch.setitem(
        status_metadata.ELASTICSEARCH_CONNECTIONS,
        "renamed_tunnel",
        {"host": "http://localhost:9200", "headers": {}, "forwarded_environment": " Test "},
    )

    assert status_metadata.get_elasticsearch_connection_label("renamed_tunnel", "prod") == "test_cluster_forwarded"


@pytest.mark.parametrize("environment", [None, "", "staging"])
def test_forwarded_target_without_known_environment_does_not_guess(monkeypatch, environment):
    monkeypatch.setitem(
        status_metadata.ELASTICSEARCH_CONNECTIONS,
        "unidentified_tunnel",
        {"forwarded_environment": environment},
    )

    assert status_metadata.get_elasticsearch_connection_label("unidentified_tunnel", "ci") == "unknown_cluster_forwarded"
    assert status_metadata.get_elasticsearch_connection_label("missing", "ci") == "unknown"


@pytest.mark.asyncio
async def test_connection_label_does_not_mutate_or_refetch_cached_metadata(monkeypatch):
    collector = AsyncMock(return_value={"elasticsearch": {"connection": "in_cluster", "sources": {}}})
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    application = SimpleNamespace(ctx=SimpleNamespace(), config=SimpleNamespace(DEPLOYMENT_ENVIRONMENT="ci"))
    annotator = SimpleNamespace(api_host="https://example.test", elasticsearch_connection="in_cluster")

    first = await status_metadata.get_backend_metadata(application, annotator)
    application.config.DEPLOYMENT_ENVIRONMENT = "test"
    second = await status_metadata.get_backend_metadata(application, annotator)

    assert first["elasticsearch"]["connection"] == "ci_cluster"
    assert second["elasticsearch"]["connection"] == "test_cluster"
    assert (await application.ctx.backend_metadata_cache.get())["elasticsearch"]["connection"] == "in_cluster"
    collector.assert_awaited_once()


@pytest.mark.asyncio
async def test_metadata_failure_does_not_fail_live_status(application_configuration, monkeypatch):
    application = build_application(application_configuration)
    collector = AsyncMock(side_effect=RuntimeError("private connection details"))
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    with patch.object(
        Annotator, "annotate_curie", new=AsyncMock(return_value={"NCBIGene:1017": [{"_id": "1017"}]})
    ):
        _, response = await application.asgi_client.get("/status")

    assert response.status_code == 200
    assert response.json["status"] == "running"
    assert set(response.json["available_query_backends"]) == {"biothings-api", "elasticsearch"}
    assert response.json["available_query_backends"]["biothings-api"]["error"] == {"code": "metadata_unavailable"}
    assert response.json["available_query_backends"]["elasticsearch"]["error"] == {"code": "metadata_unavailable"}
    assert "private connection details" not in response.text


@pytest.mark.asyncio
async def test_status_health_is_checked_again_after_worker_restart(application_configuration, monkeypatch):
    application = build_application(application_configuration)
    collector = AsyncMock(return_value={"biothings": {"sources": {}}, "elasticsearch": {"sources": {}}})
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    annotation = AsyncMock(side_effect=[{"NCBIGene:1017": [{"_id": "1017"}]}, {}, {"NCBIGene:1017": []}])
    with patch.object(Annotator, "annotate_curie", new=annotation):
        _, first = await application.asgi_client.get("/status")
        _, failed = await application.asgi_client.get("/status")
        _, recovered = await application.asgi_client.get("/status")

    assert [first.status_code, failed.status_code, recovered.status_code] == [200, 500, 200]
    assert annotation.await_count == 3
    collector.assert_awaited_once()
