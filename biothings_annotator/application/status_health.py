"""Share brief annotation health results between GET and HEAD status probes."""

import asyncio
import logging
from contextlib import suppress
from time import monotonic


logger = logging.getLogger(__name__)
HEALTH_CACHE_TTL = 5
HEALTH_FAILURE_TTL = 1
HEALTH_TIMEOUT = 10
HEALTH_CURIE = "NCBIGene:1017"
HEALTH_ERROR_MESSAGE = "Service unavailable due to a failed health check!"


class StatusHealthCache:
    def __init__(self, annotator):
        self.configuration = (annotator.query_backend, annotator.api_host, annotator.elasticsearch_connection)
        self.annotator = annotator
        self._value = None
        self._expires_at = 0
        self._refresh = None

    async def get(self):
        if self._value is not None and monotonic() < self._expires_at:
            return self._value
        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.create_task(self._load())
        return await asyncio.shield(self._refresh)

    async def _load(self):
        try:
            annotation = await asyncio.wait_for(
                self.annotator.annotate_curie(HEALTH_CURIE, fields="_id", raw=True, include_extra=False),
                timeout=HEALTH_TIMEOUT,
            )
            self._value = (
                (200, None)
                if HEALTH_CURIE in annotation
                else (500, "Service unavailable due to a failed data check!")
            )
        except Exception:
            logger.exception("Unable to complete annotation health check")
            self._value = (400, HEALTH_ERROR_MESSAGE)
        self._expires_at = monotonic() + (HEALTH_CACHE_TTL if self._value[0] == 200 else HEALTH_FAILURE_TTL)
        return self._value

    async def close(self):
        if self._refresh is not None:
            self._refresh.cancel()
            with suppress(asyncio.CancelledError):
                await self._refresh
        self._refresh = None
        self._value = None
        self._expires_at = 0


async def get_status_health(application, annotator):
    configuration = (annotator.query_backend, annotator.api_host, annotator.elasticsearch_connection)
    cache = getattr(application.ctx, "status_health_cache", None)
    if cache is None or cache.configuration != configuration:
        if cache is not None:
            await cache.close()
        cache = StatusHealthCache(annotator)
        application.ctx.status_health_cache = cache
    return await cache.get()
