"""
Collection of miscellaenous utility methods for the biothings_annotator package
"""

import asyncio
import logging
from typing import Dict, List, Optional, Union

try:
    from itertools import batched  # new in Python 3.12
except ImportError:
    from itertools import islice

    def batched(iterable, n):
        # batched('ABCDEFG', 3) → ABC DEF G
        if n < 1:
            raise ValueError("n must be at least one")
        iterator = iter(iterable)
        while batch := tuple(islice(iterator, n)):
            yield batch


import biothings_client

from biothings_annotator.annotator.elasticsearch import ElasticsearchAnnotatorClient
from biothings_annotator.annotator.exceptions import InvalidCurieError
from biothings_annotator.annotator.settings import (
    ANNOTATOR_CLIENTS,
    BIOLINK_PREFIX_to_BioThings,
    ELASTICSEARCH_CONNECTIONS,
    ELASTICSEARCH_QUERY_BATCH_SIZE,
    ELASTICSEARCH_QUERY_SIZE,
    ELASTICSEARCH_REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


def _current_event_loop_id() -> Union[int, None]:
    """
    Return a stable cache token for the running event loop, if one exists.
    """
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def get_client(node_type: str, api_host: str) -> Union[biothings_client.AsyncBiothingClient, None]:
    """
    Attempts to lazy load the biothings-client instance

    Inputs:
    > node_type: string representing which biothings-client to load based
    off the settings.py client field
    >>> "client": {"biothing_type": "gene"},
    >>> "client": {"biothing_type": "chem"},
    >>> "client": {"biothing_type": "disease"},
    >>> "client": {"url": f"{SERVICE_PROVIDER_API_HOST}/hpo"},
    >>> "client": {"url": f"{SERVICE_PROVIDER_API_HOST}/ncit"},
    >>> "client": {"url": f"{SERVICE_PROVIDER_API_HOST}/annotator_extra"},

    For mygene, mychem, and mydisease, the instances take the corresponding `biothings_type`
    argument which should match this functions node_type
    > url: string representing the API endpoint to pull down data from the
    client's perspective. This is used for hpo, ncit, and annotator_extra as additional
    data sources used with the annotator. Default value for this is stored in the
    settings.py file

    Output:
    Returns the client instance if successful and None on failure
    """
    annotator_node = ANNOTATOR_CLIENTS.get(node_type, None)
    if annotator_node is None:
        raise ValueError(f"Unable to get annotator client with `node_type`: {node_type}")

    client_parameters = annotator_node["client"]
    client_configuration = client_parameters.get("configuration")
    client_endpoint = client_parameters.get("endpoint")
    client_instance = client_parameters.get("instance")
    current_loop_id = _current_event_loop_id()
    if client_configuration is not None and isinstance(client_configuration, dict):
        cache_key = ("configuration", tuple(sorted(client_configuration.items())), current_loop_id)
    elif client_endpoint is not None and isinstance(client_endpoint, str):
        cache_key = ("endpoint", f"{api_host}/{client_endpoint}", current_loop_id)
    else:
        cache_key = None

    if (
        client_instance is not None
        and isinstance(client_instance, biothings_client.AsyncBiothingClient)
        and client_parameters.get("instance_cache_key") == cache_key
    ):
        client = client_instance

    elif client_configuration is not None and isinstance(client_configuration, dict):
        try:
            client = biothings_client.get_async_client(**client_configuration)
        except Exception:
            logger.exception("Unable to create annotator client [%s]", client_configuration)
            client = None

    elif client_endpoint is not None and isinstance(client_endpoint, str):
        client_url = f"{api_host}/{client_endpoint}"
        try:
            client = biothings_client.get_async_client(biothing_type=None, instance=True, url=client_url)
        except Exception:
            logger.exception("Unable to create endpoint-backed annotator client [%s]", client_url)
            client = None

    else:
        raise ValueError(
            (f"Unable to to build annotator client with parameters: {client_parameters}. " "No cached client found")
        )

    # cache the client
    if isinstance(client, biothings_client.AsyncBiothingClient):
        ANNOTATOR_CLIENTS[node_type]["client"]["instance"] = client
        ANNOTATOR_CLIENTS[node_type]["client"]["instance_cache_key"] = cache_key

    return client


def get_elasticsearch_connection(elasticsearch_connection: str) -> Dict:
    """
    Return a normalized Elasticsearch connection config by name.
    """
    connection = ELASTICSEARCH_CONNECTIONS.get(elasticsearch_connection)
    if connection is None:
        raise ValueError(f"Unknown Elasticsearch connection: {elasticsearch_connection}")

    host = connection.get("host")
    if not host:
        raise ValueError(f"Missing host for Elasticsearch connection: {elasticsearch_connection}")

    return {
        "host": host,
        "headers": dict(connection.get("headers", {})),
    }


def get_elasticsearch_client(node_type: str, elasticsearch_connection: str) -> ElasticsearchAnnotatorClient:
    """
    Lazily build an Elasticsearch-backed client for annotator queries.
    """
    annotator_node = ANNOTATOR_CLIENTS.get(node_type, None)
    if annotator_node is None:
        raise ValueError(f"Unable to get annotator client with `node_type`: {node_type}")

    elasticsearch_parameters = annotator_node.get("elasticsearch", {})
    elasticsearch_index = elasticsearch_parameters.get("index")
    if not elasticsearch_index:
        raise ValueError(f"Missing Elasticsearch index configuration for `node_type`: {node_type}")

    connection = get_elasticsearch_connection(elasticsearch_connection)
    elasticsearch_host = connection["host"]
    elasticsearch_headers = connection["headers"]

    client_instance = elasticsearch_parameters.get("instance")
    if (
        isinstance(client_instance, ElasticsearchAnnotatorClient)
        and client_instance.host == elasticsearch_host.rstrip("/")
        and client_instance.headers == elasticsearch_headers
    ):
        return client_instance

    client = ElasticsearchAnnotatorClient(
        host=elasticsearch_host,
        index=elasticsearch_index,
        query_size=ELASTICSEARCH_QUERY_SIZE,
        query_batch_size=ELASTICSEARCH_QUERY_BATCH_SIZE,
        timeout=ELASTICSEARCH_REQUEST_TIMEOUT,
        headers=elasticsearch_headers,
    )
    ANNOTATOR_CLIENTS[node_type]["elasticsearch"]["instance"] = client
    return client


def get_query_client(
    node_type: str,
    query_backend: str,
    api_host: str,
    elasticsearch_connection: Optional[str] = None,
) -> Union[biothings_client.AsyncBiothingClient, ElasticsearchAnnotatorClient, None]:
    """
    Return the configured annotator query client.
    """
    if query_backend == "biothings":
        return get_client(node_type, api_host)
    if query_backend == "elasticsearch":
        if not elasticsearch_connection:
            raise ValueError("Missing Elasticsearch connection for Elasticsearch query backend")
        return get_elasticsearch_client(node_type, elasticsearch_connection)

    raise ValueError(f"Unsupported annotator query backend: {query_backend}")


def parse_curie(curie: str, return_type: bool = True, return_id: bool = True):
    """
    return both type and if (as a tuple) or either based on the input curie
    """
    if ":" not in curie:
        raise InvalidCurieError(curie)

    _prefix, _id = curie.split(":", 1)
    _type = BIOLINK_PREFIX_to_BioThings.get(_prefix, {}).get("type", None)
    if return_id:
        if not _type or BIOLINK_PREFIX_to_BioThings[_prefix].get("keep_prefix", False):
            _id = curie
        cvtr = BIOLINK_PREFIX_to_BioThings.get(_prefix, {}).get("converter", None)
        if cvtr:
            _id = cvtr(curie)
    if return_type and return_id:
        return _type, _id
    elif return_type:
        return _type
    elif return_id:
        return _id


def group_by_subfield(collection: List[Dict], search_key: str) -> Dict:
    """
    Takes a collection of dictionary entries with a specify subfield key "search_key" and
    extracts the subfield from each entry in the iterable into a dictionary.

    It the bins entries into the dictionary so that identical keys have all results in one
    aggregated list across the entire collection of dictionary entries

    Example:

    - 1 Entry
    search_key = "query"
    collection = [
        {
            'query': '8199',
            '_id': '84557',
            '_score': 1.55,
            'name': 'microtubule associated protein 1 light chain 3 alpha'
        }
    ]

    ... (Processing)

    sub_field_collection = {
        '8199': [
            {
                'query': '8199',
                '_id': '84557',
                '_score': 1.55,
                'name': 'microtubule associated protein 1 light chain 3 alpha'
            }
        ]
    }

    """
    sub_field_collection = {}
    for sub_mapping in collection:
        sub_field = sub_mapping.get(search_key, None)
        if sub_field is not None:
            sub_field_aggregation = sub_field_collection.setdefault(sub_field, [])
            sub_field_aggregation.append(sub_mapping)
    return sub_field_collection


def get_dotfield_value(dotfield: str, d: Dict):
    """
    Explore dictionary d using dotfield notation and return value.
    Example::

        d = {"a":{"b":1}}.
        get_dotfield_value("a.b",d) => 1

    Taken from the biothings.api repository as this method was the sole
    dependency from the package. This should make our dependencies a lot leaner
    biothings.api path: biothings.utils.common -> get_dotfield_value
    """
    fields = dotfield.split(".")
    if len(fields) == 1:
        return d[fields[0]]
    else:
        first = fields[0]
        return get_dotfield_value(".".join(fields[1:]), d[first])
