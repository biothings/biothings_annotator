"""Briefly cache backend metadata without caching the live health check."""

import asyncio
import logging
from datetime import datetime, timezone
from time import monotonic

from biothings_annotator.annotator.settings import ELASTICSEARCH_CONNECTIONS
from biothings_annotator.annotator.source_metadata import collect_backend_metadata


logger = logging.getLogger(__name__)
METADATA_CACHE_TTL = 60


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
    backends = await cache.get()
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
