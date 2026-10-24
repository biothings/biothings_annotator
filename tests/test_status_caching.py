"""Background source snapshots and short health caching remain independent."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sanic import Sanic

from biothings_annotator.annotator import Annotator
from biothings_annotator.application import build_application, status_health, status_metadata
from biothings_annotator.application.cli.arguments import load_configuration
from biothings_annotator.application.status_health import StatusHealthCache, get_status_health
from biothings_annotator.application.status_metadata import BackendMetadataCache


pytestmark = pytest.mark.unit


def metadata(version):
    return {
        "biothings": {"sources": {"mygene": {"build_version": version, "sources": []}}},
        "elasticsearch": {"connection": "local", "sources": {}},
    }


def annotator():
    return SimpleNamespace(
        query_backend="biothings",
        api_host="https://example.test",
        elasticsearch_connection="local",
        annotate_curie=AsyncMock(return_value={"NCBIGene:1017": [{"_id": "1017"}]}),
    )


async def test_metadata_refresh_runs_without_requests_and_serves_snapshot_during_refresh(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    published = asyncio.Event()

    async def collect(*args):
        if collector.await_count == 1:
            return metadata("old")
        started.set()
        await release.wait()
        return metadata("new")

    collector = AsyncMock(side_effect=collect)
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    monkeypatch.setattr(status_metadata, "METADATA_REFRESH_INTERVAL", 0.001)
    cache = BackendMetadataCache("https://example.test", "local")
    original = await cache.get()
    refresh = cache.refresh

    async def refresh_and_notify():
        result = await refresh()
        published.set()
        return result

    cache.refresh = refresh_and_notify
    cache.start()
    task = cache._background
    cache.start()
    assert cache._background is task
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert await asyncio.wait_for(cache.get(), timeout=0.1) == original
        release.set()
        await asyncio.wait_for(published.wait(), timeout=1)
        assert (await cache.get())["biothings-api"]["sources"]["mygene"]["build_version"] == "new"
    finally:
        await cache.close()
    assert task.cancelled()


async def test_collection_failure_retains_snapshot_timestamp_and_recovers(monkeypatch):
    collector = AsyncMock(side_effect=[metadata("old"), RuntimeError("private upstream URL"), metadata("new")])
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    cache = BackendMetadataCache("https://example.test", "local")
    previous = deepcopy(await cache.get())

    failed = await cache.refresh()

    for backend in previous:
        assert failed[backend] == {**previous[backend], "refresh_error": {"code": "metadata_unavailable"}}
    assert cache._retry
    recovered = await cache.refresh()
    assert recovered["biothings-api"]["sources"]["mygene"]["build_version"] == "new"
    assert all("refresh_error" not in backend for backend in recovered.values())
    assert not cache._retry


async def test_background_retries_collection_failure_before_normal_interval(monkeypatch):
    collector = AsyncMock(side_effect=[RuntimeError("temporary failure"), metadata("recovered")])
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    monkeypatch.setattr(status_metadata, "METADATA_REFRESH_INTERVAL", 60)
    monkeypatch.setattr(status_metadata, "METADATA_RETRY_INTERVAL", 0.001)
    cache = BackendMetadataCache("https://example.test", "local")
    await cache.get()
    recovered = asyncio.Event()
    refresh = cache.refresh

    async def refresh_and_notify():
        result = await refresh()
        recovered.set()
        return result

    cache.refresh = refresh_and_notify
    cache.start()
    try:
        await asyncio.wait_for(recovered.wait(), timeout=1)
        assert (await cache.get())["biothings-api"]["sources"]["mygene"]["build_version"] == "recovered"
        assert collector.await_count == 2
    finally:
        await cache.close()


@pytest.mark.parametrize(
    "error,retry",
    [
        ({"code": "timeout"}, True),
        ({"code": "connection_error"}, True),
        ({"code": "http_error", "http_status": 503}, True),
        ({"code": "http_error", "http_status": 429}, True),
        ({"code": "http_error", "http_status": 404}, False),
        ({"code": "configuration_error"}, False),
        ({"code": "multiple_indices"}, False),
    ],
)
async def test_source_errors_remain_local_and_only_transient_errors_retry_soon(monkeypatch, error, retry):
    snapshot = metadata("healthy")
    snapshot["biothings"]["sources"]["optional"] = {"error": error}
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", AsyncMock(return_value=snapshot))
    cache = BackendMetadataCache("https://example.test", "local")

    result = await cache.get()

    assert result["biothings-api"]["sources"]["mygene"]["build_version"] == "healthy"
    assert result["biothings-api"]["sources"]["optional"] == {"error": error}
    assert cache._retry is retry


async def test_metadata_deadline_is_informational_and_shutdown_cancels_work(monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def collect(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(status_metadata, "collect_backend_metadata", AsyncMock(side_effect=collect))
    monkeypatch.setattr(status_metadata, "METADATA_REFRESH_TIMEOUT", 0.001)
    cache = BackendMetadataCache("https://example.test", "local")
    result = await asyncio.wait_for(cache.get(), timeout=1)
    assert all(backend["error"] == {"code": "metadata_unavailable"} for backend in result.values())
    assert cancelled.is_set()
    cancelled.clear()
    started.clear()
    monkeypatch.setattr(status_metadata, "METADATA_REFRESH_TIMEOUT", 10)
    refresh = asyncio.create_task(cache.refresh())
    await started.wait()
    await cache.close()
    with pytest.raises(asyncio.CancelledError):
        await refresh
    assert cancelled.is_set()


async def test_configuration_change_stops_previous_metadata_timer(monkeypatch):
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", AsyncMock(return_value=metadata("v1")))
    app = SimpleNamespace(
        ctx=SimpleNamespace(status_background_started=True), config=SimpleNamespace(DEPLOYMENT_ENVIRONMENT="local")
    )
    current = annotator()
    await status_metadata.get_backend_metadata(app, current)
    previous = app.ctx.backend_metadata_cache
    task = previous._background
    current.api_host = "https://another.test"
    try:
        await status_metadata.get_backend_metadata(app, current)
        assert app.ctx.backend_metadata_cache is not previous
        assert task.cancelled()
    finally:
        await app.ctx.backend_metadata_cache.close()


async def test_health_cache_expiry_failure_backoff_and_recovery(monkeypatch):
    current = annotator()
    current.annotate_curie.side_effect = [{"NCBIGene:1017": []}, {}, {"NCBIGene:1017": []}]
    cache = StatusHealthCache(current)
    monkeypatch.setattr(status_health, "monotonic", lambda: 0)
    assert await cache.get() == (200, None)
    monkeypatch.setattr(status_health, "monotonic", lambda: 4.99)
    assert await cache.get() == (200, None)
    assert current.annotate_curie.await_count == 1
    monkeypatch.setattr(status_health, "monotonic", lambda: 5)
    assert (await cache.get())[0] == 500
    assert (await cache.get())[0] == 500
    assert current.annotate_curie.await_count == 2
    monkeypatch.setattr(status_health, "monotonic", lambda: 6)
    assert await cache.get() == (200, None)


async def test_health_refresh_is_shared_and_survives_caller_cancellation():
    started = asyncio.Event()
    release = asyncio.Event()
    current = annotator()

    async def annotate(*args, **kwargs):
        started.set()
        await release.wait()
        return {"NCBIGene:1017": []}

    current.annotate_curie.side_effect = annotate
    cache = StatusHealthCache(current)
    first = asyncio.create_task(cache.get())
    second = asyncio.create_task(cache.get())
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == (200, None)
    assert current.annotate_curie.await_count == 1


async def test_health_exception_details_are_logged_without_exposing_them_in_cached_results(monkeypatch, caplog):
    private_error = RuntimeError(
        "http://service-user:private-password@elasticsearch.internal:9200/private-index "
        "returned body: {\"access_token\": \"private-token\"}"
    )
    current = annotator()
    current.annotate_curie.side_effect = private_error
    monkeypatch.setattr(status_health, "monotonic", lambda: 0)
    cache = StatusHealthCache(current)

    with caplog.at_level("ERROR", logger=status_health.__name__):
        result = await cache.get()
        cached_result = await cache.get()

    assert result == cached_result == (400, "Service unavailable due to a failed health check!")
    for private_detail in ("elasticsearch.internal", "private-index", "private-password", "private-token"):
        assert private_detail not in result[1]
    current.annotate_curie.assert_awaited_once()
    records = [record for record in caplog.records if record.name == status_health.__name__]
    assert len(records) == 1
    assert records[0].message == "Unable to complete annotation health check"
    assert records[0].exc_info[1] is private_error
    assert str(private_error) in caplog.text


@pytest.mark.parametrize("setting", ["query_backend", "api_host", "elasticsearch_connection"])
async def test_health_cache_is_scoped_to_application_and_backend_configuration(setting):
    app = SimpleNamespace(ctx=SimpleNamespace())
    current = annotator()
    assert await get_status_health(app, current) == (200, None)
    assert await get_status_health(app, current) == (200, None)
    assert current.annotate_curie.await_count == 1
    setattr(current, setting, "changed")
    assert await get_status_health(app, current) == (200, None)
    assert current.annotate_curie.await_count == 2
    assert await get_status_health(SimpleNamespace(ctx=SimpleNamespace()), current) == (200, None)
    assert current.annotate_curie.await_count == 3


async def test_health_deadline_returns_safe_exception_failure_shape(monkeypatch):
    monkeypatch.setattr(status_health, "HEALTH_TIMEOUT", 0.001)
    current = annotator()

    async def never_returns(*args, **kwargs):
        await asyncio.Event().wait()

    current.annotate_curie.side_effect = never_returns
    result = await asyncio.wait_for(StatusHealthCache(current).get(), timeout=1)
    assert result == (400, "Service unavailable due to a failed health check!")


async def test_get_and_head_share_health_during_worker_lifetime_and_stop_tasks(monkeypatch):
    monkeypatch.setattr(Sanic, "_app_registry", {})
    application = build_application(load_configuration())
    client = application.asgi_client
    await application._startup()
    await application._server_event("init", "before")
    await application._server_event("init", "after")
    cache = application.ctx.backend_metadata_cache
    background = cache._background
    annotation = AsyncMock(side_effect=[{"NCBIGene:1017": []}, {}])
    try:
        # The ASGI test client normally stops and restarts the worker for each
        # request. Keep it running here to test caching across real GET and HEAD.
        with patch.object(Sanic, "_server_event", new=AsyncMock()), patch.object(
            Annotator, "annotate_curie", new=annotation
        ):
            monkeypatch.setattr(status_health, "monotonic", lambda: 0)
            _, first = await client.get("/status")
            _, head = await client.head("/status")
            assert first.status_code == head.status_code == 200
            assert head.body == b""
            assert annotation.await_count == 1
            monkeypatch.setattr(status_health, "monotonic", lambda: 5)
            _, failed = await client.get("/status")
            _, failed_head = await client.head("/status")
            assert failed.status_code == failed_head.status_code == 500
            assert failed.json == {"success": False, "error": "Service unavailable due to a failed data check!"}
            assert annotation.await_count == 2
            for response in (first, head, failed, failed_head):
                assert response.headers["Cache-Control"] == "no-store"
    finally:
        await application._server_event("shutdown", "before")
        await application._server_event("shutdown", "after")
    assert background.cancelled()
    assert application.ctx.status_health_cache._value is None
