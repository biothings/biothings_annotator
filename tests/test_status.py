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
        return {"biothings": {"datasets": {}}, "elasticsearch": {"datasets": {}}}

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
    assert datetime.fromisoformat(result["biothings"]["checked_at"]).tzinfo is not None


@pytest.mark.asyncio
async def test_metadata_cache_expires_and_replaces_failed_metadata(monkeypatch):
    failed = {"biothings": {"datasets": {"gene": {"error": {"code": "timeout"}}}}}
    recovered = {"biothings": {"datasets": {"gene": {"build_version": "new"}}}}
    collector = AsyncMock(side_effect=[failed, recovered])
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    monkeypatch.setattr(status_metadata, "monotonic", lambda: 0)
    cache = status_metadata.BackendMetadataCache("https://example.test", "local")

    assert (await cache.get())["biothings"]["datasets"] == failed["biothings"]["datasets"]
    monkeypatch.setattr(status_metadata, "monotonic", lambda: status_metadata.METADATA_CACHE_TTL - 1)
    assert (await cache.get())["biothings"]["datasets"] == failed["biothings"]["datasets"]
    assert collector.await_count == 1

    monkeypatch.setattr(status_metadata, "monotonic", lambda: status_metadata.METADATA_CACHE_TTL)
    assert (await cache.get())["biothings"]["datasets"] == recovered["biothings"]["datasets"]
    assert collector.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setting,new_value", [("api_host", "https://other.test"), ("elasticsearch_connection", "test_forward")]
)
async def test_metadata_cache_is_scoped_to_application_and_backend_configuration(monkeypatch, setting, new_value):
    collector = AsyncMock(return_value={"biothings": {"datasets": {}}, "elasticsearch": {"datasets": {}}})
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
    assert response.json["backends"]["biothings"]["error"] == {"code": "metadata_unavailable"}
    assert response.json["backends"]["elasticsearch"]["error"] == {"code": "metadata_unavailable"}
    assert "private connection details" not in response.text


@pytest.mark.asyncio
async def test_cached_metadata_does_not_cache_the_health_probe(application_configuration, monkeypatch):
    application = build_application(application_configuration)
    collector = AsyncMock(return_value={"biothings": {"datasets": {}}, "elasticsearch": {"datasets": {}}})
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    annotation = AsyncMock(side_effect=[{"NCBIGene:1017": [{"_id": "1017"}]}, {}, {"NCBIGene:1017": []}])
    with patch.object(Annotator, "annotate_curie", new=annotation):
        _, first = await application.asgi_client.get("/status")
        _, failed = await application.asgi_client.get("/status")
        _, recovered = await application.asgi_client.get("/status")

    assert [first.status_code, failed.status_code, recovered.status_code] == [200, 500, 200]
    assert annotation.await_count == 3
    collector.assert_awaited_once()
