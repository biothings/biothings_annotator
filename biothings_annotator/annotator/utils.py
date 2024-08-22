"""
Collection of miscellaenous utility methods for the biothings_annotator package
"""

import logging
from typing import Union

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

from .exceptions import InvalidCurieError
from .settings import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings

logger = logging.getLogger(__name__)


def get_client(node_type: str, api_host: str) -> Union[biothings_client.BiothingClient, None]:
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

    if client_instance is not None and isinstance(client_instance, biothings_client.BiothingClient):
        client = client_instance

    elif client_configuration is not None and isinstance(client_configuration, dict):
        try:
            client = biothings_client.get_client(**client_configuration)
        except RuntimeError as runtime_error:
            logger.error("%s [%s]", runtime_error, client_configuration)
            client = None

    elif client_endpoint is not None and isinstance(client_endpoint, str):
        client_url = f"{api_host}/{client_endpoint}"
        try:
            client = biothings_client.get_client(biothing_type=None, instance=True, url=client_url)
        except RuntimeError as runtime_error:
            logger.error("%s [%s]", runtime_error, client_url)
            client = None

    else:
        raise ValueError(
            (f"Unable to to build annotator client with parameters: {client_parameters}. " "No cached client found")
        )

    # cache the client
    if isinstance(client, biothings_client.BiothingClient):
        ANNOTATOR_CLIENTS[node_type]["client"]["instance"] = client

    return client


def parse_curie(curie: str, return_type: bool = True, return_id: bool = True):
    """
    return a both type and if (as a tuple) or either based on the input curie
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


def group_by_subfield(collection: list[dict], search_key: str) -> dict:
    """
    Takes a collection of dictionary entries with a specify subfield key "search_key" and
    extracts the subfield from each entry in the iterable into a dictionary.

    It then bins entries into the dictionary so that identical keys have all results in one
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


def get_dotfield_value(dotfield: str, d: dict):
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
        return get_dotfield_value(".".join(fields[1:]), d[first])
