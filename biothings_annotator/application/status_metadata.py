"""Refresh informational backend metadata independently of status requests."""

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone
from types import SimpleNamespace

from biothings_annotator.annotator.settings import (
    DEFAULT_ELASTICSEARCH_CONNECTION,
    ELASTICSEARCH_CONNECTIONS,
    SERVICE_PROVIDER_API_HOST,
)
from biothings_annotator.annotator.source_metadata import collect_backend_metadata


logger = logging.getLogger(__name__)
METADATA_REFRESH_INTERVAL = 600
METADATA_RETRY_INTERVAL = 30
METADATA_REFRESH_TIMEOUT = 10


def get_elasticsearch_connection_label(connection_name: str, deployment_environment: str) -> str:
    """Describe the configured cluster target without claiming verified identity."""
    if connection_name == "in_cluster":
        environment = deployment_environment
        suffix = "cluster"
    else:
        connection = ELASTICSEARCH_CONNECTIONS.get(connection_name, {})
        if "forwarded_environment" not in connection:
            return "local" if connection_name == "local" else "unknown"
        environment = connection["forwarded_environment"]
        suffix = "cluster_forwarded"

    environment = environment.strip().lower() if isinstance(environment, str) else "unknown"
    if environment not in {"ci", "test", "prod"}:
        environment = "unknown"
    return f"{environment}_{suffix}"


class BackendMetadataCache:
    def __init__(self, api_host: str, elasticsearch_connection: str):
        self.configuration = (api_host, elasticsearch_connection)
        self._value = None
        self._refresh = None
        self._background = None
        self._retry = False
        self._retry_delay = METADATA_RETRY_INTERVAL

    async def get(self):
        if self._value is not None:
            return self._value
        return await self.refresh()

    async def refresh(self):
        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.create_task(self._load())
        # A disconnected caller must not cancel a refresh shared by other probes.
        return await asyncio.shield(self._refresh)

    async def _load(self):
        try:
            backends = await asyncio.wait_for(
                collect_backend_metadata(*self.configuration), timeout=METADATA_REFRESH_TIMEOUT
            )
        except Exception:
            # Metadata is informational; the annotation probe determines health.
            logger.exception("Unable to collect backend source metadata")
            self._update_retry(True)
            if self._value is None:
                checked_at = datetime.now(timezone.utc).isoformat()
                self._value = {
                    backend: {"error": {"code": "metadata_unavailable"}, "checked_at": checked_at}
                    for backend in ("biothings-api", "elasticsearch")
                }
            else:
                self._value = {
                    backend: {**metadata, "refresh_error": {"code": "metadata_unavailable"}}
                    for backend, metadata in self._value.items()
                }
            return self._value

        self._update_retry(
            any(
                self._is_transient_error(source.get("error", {}))
                for metadata in backends.values()
                for source in metadata.get("sources", {}).values()
            )
        )
        checked_at = datetime.now(timezone.utc).isoformat()
        self._value = {
            "biothings-api" if backend == "biothings" else backend: {**metadata, "checked_at": checked_at}
            for backend, metadata in backends.items()
        }
        return self._value

    def _update_retry(self, retry):
        if retry and self._retry:
            self._retry_delay = min(self._retry_delay * 2, METADATA_REFRESH_INTERVAL)
        else:
            self._retry_delay = min(METADATA_RETRY_INTERVAL, METADATA_REFRESH_INTERVAL)
        self._retry = retry

    @staticmethod
    def _is_transient_error(error):
        return error.get("code") in {"timeout", "connection_error", "metadata_unavailable"} or (
            error.get("code") == "http_error"
            and (error.get("http_status", 0) >= 500 or error.get("http_status") == 429)
        )

    async def _run(self):
        while True:
            await asyncio.sleep(self._retry_delay if self._retry else METADATA_REFRESH_INTERVAL)
            await self.refresh()

    def start(self):
        if self._background is None or self._background.done():
            self._background = asyncio.create_task(self._run())

    async def close(self):
        for task in (self._background, self._refresh):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self._background = None
        self._refresh = None


async def get_metadata_cache(application, annotator):
    configuration = (annotator.api_host, annotator.elasticsearch_connection)
    cache = getattr(application.ctx, "backend_metadata_cache", None)
    if cache is None or cache.configuration != configuration:
        if cache is not None:
            await cache.close()
        cache = BackendMetadataCache(*configuration)
        application.ctx.backend_metadata_cache = cache
    return cache


async def start_status_tasks(application, _loop):
    # Metadata covers both backends and must not depend on whether the default
    # annotation backend is valid. Query handlers retain their configuration errors.
    configuration = SimpleNamespace(
        api_host=os.environ.get("SERVICE_PROVIDER_API_HOST", SERVICE_PROVIDER_API_HOST),
        elasticsearch_connection=os.environ.get("ELASTICSEARCH_CONNECTION", DEFAULT_ELASTICSEARCH_CONNECTION).strip(),
    )
    cache = await get_metadata_cache(application, configuration)
    await cache.get()
    cache.start()
    application.ctx.status_background_started = True


async def stop_status_tasks(application, _loop):
    application.ctx.status_background_started = False
    for attribute in ("backend_metadata_cache", "status_health_cache"):
        cache = getattr(application.ctx, attribute, None)
        if cache is not None:
            await cache.close()


async def get_backend_metadata(application, annotator):
    cache = await get_metadata_cache(application, annotator)
    backends = await cache.get()
    if getattr(application.ctx, "status_background_started", False):
        cache.start()
    elasticsearch = backends.get("elasticsearch", {})
    if "connection" not in elasticsearch:
        return backends
    # Format after reading the cache so deployment labels never mutate the
    # collected metadata or borrow an environment from another application.
    return {
        **backends,
        "elasticsearch": {
            **elasticsearch,
            "connection": get_elasticsearch_connection_label(
                annotator.elasticsearch_connection, application.config.DEPLOYMENT_ENVIRONMENT
            ),
        },
    }
