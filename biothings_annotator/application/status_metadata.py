"""Briefly cache backend metadata without caching the live health check."""

import asyncio
import logging
from datetime import datetime, timezone
from time import monotonic

from biothings_annotator.annotator.source_metadata import collect_backend_metadata


logger = logging.getLogger(__name__)
METADATA_CACHE_TTL = 60


class BackendMetadataCache:
    def __init__(self, api_host: str, elasticsearch_connection: str):
        self.configuration = (api_host, elasticsearch_connection)
        self._value = None
        self._expires_at = 0
        self._refresh = None

    async def get(self):
        if self._value is not None and monotonic() < self._expires_at:
            return self._value
        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.create_task(self._load())
        # A disconnected caller must not cancel a refresh shared by other probes.
        return await asyncio.shield(self._refresh)

    async def _load(self):
        try:
            backends = await collect_backend_metadata(*self.configuration)
        except Exception:
            # Metadata is informational; the annotation probe determines health.
            logger.exception("Unable to collect backend source metadata")
            backends = {
                backend: {"error": {"code": "metadata_unavailable"}}
                for backend in ("biothings", "elasticsearch")
            }
        checked_at = datetime.now(timezone.utc).isoformat()
        self._value = {
            "biothings-api" if backend == "biothings" else backend: {**metadata, "checked_at": checked_at}
            for backend, metadata in backends.items()
        }
        self._expires_at = monotonic() + METADATA_CACHE_TTL
        return self._value


async def get_backend_metadata(application, annotator):
    configuration = (annotator.api_host, annotator.elasticsearch_connection)
    cache = getattr(application.ctx, "backend_metadata_cache", None)
    if cache is None or cache.configuration != configuration:
        cache = BackendMetadataCache(*configuration)
        application.ctx.backend_metadata_cache = cache
    return await cache.get()
