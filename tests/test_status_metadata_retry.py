"""Persistent metadata failures back off without changing cached source results."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from biothings_annotator.application import status_metadata
from biothings_annotator.application.status_metadata import BackendMetadataCache


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("collection_failure", [False, True])
async def test_background_retry_backs_off_caps_and_resets_after_recovery(monkeypatch, collection_failure):
    healthy = {
        "biothings": {"sources": {"mygene": {"build_version": "current", "sources": []}}},
        "elasticsearch": {"sources": {"mygene": {"alias": "gene", "index": {"name": "gene_v1"}}}},
    }
    unreachable = deepcopy(healthy)
    unreachable["elasticsearch"]["sources"]["mygene"] = {"alias": "gene", "error": {"code": "connection_error"}}
    permanent = deepcopy(healthy)
    permanent["elasticsearch"]["sources"]["mygene"] = {
        "alias": "gene",
        "error": {"code": "http_error", "http_status": 404},
    }
    failure = RuntimeError("unreachable internal host") if collection_failure else unreachable
    collector = AsyncMock(side_effect=[healthy, *([failure] * 7), healthy, failure, permanent])
    monkeypatch.setattr(status_metadata, "collect_backend_metadata", collector)
    cache = BackendMetadataCache("https://example.test", "local")
    previous = await cache.get()
    await cache.refresh()
    delays = []
    snapshots = []

    async def scheduled_sleep(delay):
        delays.append(delay)
        snapshots.append(deepcopy(await cache.get()))
        if len(delays) == 10:
            raise asyncio.CancelledError

    monkeypatch.setattr(status_metadata.asyncio, "sleep", scheduled_sleep)
    try:
        with pytest.raises(asyncio.CancelledError):
            await cache._run()

        assert delays == [30, 60, 120, 240, 480, 600, 600, 600, 30, 600]
        assert collector.await_count == 11
        for snapshot in snapshots:
            assert snapshot["biothings-api"]["sources"]["mygene"]["build_version"] == "current"
        if collection_failure:
            assert snapshots[0]["biothings-api"]["checked_at"] == previous["biothings-api"]["checked_at"]
            assert snapshots[0]["biothings-api"]["refresh_error"] == {"code": "metadata_unavailable"}
        else:
            assert snapshots[0]["elasticsearch"]["sources"]["mygene"]["error"] == {"code": "connection_error"}
        assert "refresh_error" not in snapshots[7]["biothings-api"]
        assert snapshots[7]["elasticsearch"]["sources"] == healthy["elasticsearch"]["sources"]
        assert snapshots[-1]["elasticsearch"]["sources"] == permanent["elasticsearch"]["sources"]
    finally:
        await cache.close()
