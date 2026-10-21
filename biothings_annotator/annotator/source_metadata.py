"""Best-effort source versions from each configured annotation backend."""

import asyncio
from typing import Dict, Optional
from urllib.parse import quote

import biothings_client
import httpx

from biothings_annotator.annotator.settings import ANNOTATOR_CLIENTS, SUPPORTED_QUERY_BACKENDS
from biothings_annotator.annotator.utils import get_elasticsearch_connection


SOURCE_METADATA_TIMEOUT = 5.0


def _version(value: object) -> Optional[str]:
    """Keep supplied scalar versions, leaving absent or structured values unknown."""
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _normalize_metadata(payload: object) -> Dict:
    if not isinstance(payload, dict):
        raise ValueError("Metadata must be an object")
    return {"build_version": _version(payload.get("build_version"))}


def _normalize_indices(payload: object) -> Dict:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Elasticsearch metadata must identify at least one index")
    indices = {}
    for index, details in payload.items():
        if not isinstance(details, dict):
            raise ValueError("Elasticsearch index metadata must be an object")
        mappings = details.get("mappings", {})
        if not isinstance(mappings, dict):
            raise ValueError("Elasticsearch mappings must be an object")
        metadata = mappings.get("_meta", {})
        # A response anchor identifies an index even when its mapping has no
        # _meta. Its name alone is not evidence of an upstream build version.
        indices[index] = _normalize_metadata(metadata)
    return {"indices": indices}


def _base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = httpx.URL(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise ValueError("Metadata endpoint must use HTTP or HTTPS")
    return normalized


def _biothings_metadata_url(configuration: Dict, api_host: str) -> str:
    client_configuration = configuration.get("configuration")
    if isinstance(client_configuration, dict):
        # The SDK performs a synchronous metadata request if the type is absent.
        # Explicitly typed clients only resolve their configured/default URL.
        biothing_type = client_configuration.get("biothing_type")
        if not isinstance(biothing_type, str) or not biothing_type.strip():
            raise ValueError("A typed BioThings client is required")
        client = biothings_client.get_async_client(**client_configuration)
        return f"{_base_url(client.url)}/metadata"

    endpoint = configuration.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("A BioThings endpoint is required")
    return f"{_base_url(api_host)}/{endpoint.strip('/')}/metadata"


def _error(code: str, http_status: Optional[int] = None) -> Dict:
    error = {"code": code}
    if http_status is not None:
        error["http_status"] = http_status
    return {"error": error}


async def _fetch_metadata(client: httpx.AsyncClient, url: str, normalize, **kwargs) -> Dict:
    async def fetch() -> Dict:
        response = await client.get(url, **kwargs)
        response.raise_for_status()
        return normalize(response.json())

    try:
        # HTTPX's phase timeouts do not impose a total wall-clock deadline.
        return await asyncio.wait_for(fetch(), timeout=SOURCE_METADATA_TIMEOUT)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return _error("timeout")
    except httpx.HTTPStatusError as exc:
        return _error("http_error", exc.response.status_code)
    except httpx.RequestError:
        return _error("connection_error")
    except (ValueError, TypeError):
        return _error("invalid_metadata")


async def _biothings_dataset(client: httpx.AsyncClient, settings: Dict, api_host: str) -> Dict:
    try:
        url = _biothings_metadata_url(settings["client"], api_host)
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, httpx.InvalidURL):
        return _error("configuration_error")
    return await _fetch_metadata(client, url, _normalize_metadata)


async def _elasticsearch_dataset(
    client: httpx.AsyncClient,
    settings: Dict,
    elasticsearch_connection: str,
) -> Dict:
    result = {"index": None}
    try:
        index = settings.get("elasticsearch", {}).get("index")
        result["index"] = index
        if not isinstance(index, str) or not index.strip():
            raise ValueError("An Elasticsearch index is required")
        connection = get_elasticsearch_connection(elasticsearch_connection)
        url = f"{_base_url(connection['host'])}/{quote(index, safe='')}"
    except (AttributeError, KeyError, TypeError, ValueError, httpx.InvalidURL):
        return {**result, **_error("configuration_error")}

    metadata = await _fetch_metadata(
        client,
        url,
        _normalize_indices,
        headers=connection["headers"],
        # UUID retains metadata-less indices in the filtered response without
        # downloading field mappings. It is not exposed or treated as a version.
        params={"filter_path": "*.mappings._meta.build_version,*.settings.index.uuid"},
    )
    return {**result, **metadata}


async def collect_backend_metadata(api_host: str, elasticsearch_connection: str) -> Dict:
    """Fetch both backends concurrently, reporting each dataset's failures locally.

    These results describe source metadata availability, not service health.
    The caller controls caching and chooses the backend used by health checks.
    """
    node_types = {
        backend: [
            node_type
            for node_type, settings in ANNOTATOR_CLIENTS.items()
            if backend in settings.get("query_backends", SUPPORTED_QUERY_BACKENDS)
        ]
        for backend in SUPPORTED_QUERY_BACKENDS
    }
    biothings_types = node_types["biothings"]
    elasticsearch_types = node_types["elasticsearch"]
    async with httpx.AsyncClient(timeout=SOURCE_METADATA_TIMEOUT, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_biothings_dataset(client, ANNOTATOR_CLIENTS[node_type], api_host) for node_type in biothings_types),
            *(
                _elasticsearch_dataset(client, ANNOTATOR_CLIENTS[node_type], elasticsearch_connection)
                for node_type in elasticsearch_types
            ),
        )
    return {
        "biothings": {"datasets": dict(zip(biothings_types, results[: len(biothings_types)]))},
        "elasticsearch": {
            "connection": elasticsearch_connection,
            "datasets": dict(zip(elasticsearch_types, results[len(biothings_types) :])),
        },
    }
