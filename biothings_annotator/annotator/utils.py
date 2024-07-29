"""
Collection of miscellaenous utility methods for the biothings_annotator package
"""
import logging

import biothings_client

from .exceptions import InvalidCurieError
from .settings import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings

logger = logging.getLogger(__name__)


def get_client(node_type: str) -> tuple[biothings_client.BiothingClient, None]:
    """
    lazy load the biothings client for the given node_type, return the client or None if failed.
    """
    client_or_kwargs = ANNOTATOR_CLIENTS[node_type]["client"]
    if isinstance(client_or_kwargs, biothings_client.BiothingClient):
        client = client_or_kwargs
    elif isinstance(client_or_kwargs, dict):
        try:
            client = biothings_client.get_client(**client_or_kwargs)
        except RuntimeError as e:
            logger.error("%s [%s]", e, client_or_kwargs)
            client = None
        if isinstance(client, biothings_client.BiothingClient):
            # cache the client
            ANNOTATOR_CLIENTS[node_type]["client"] = client
    else:
        raise ValueError("Invalid input client_or_kwargs")
    return client


def parse_curie(curie: str, return_type: bool = True, return_id: bool = True):
    """
    return a both type and if (as a tuple) or either based on the input curie
    """
    if ":" not in curie:
        raise InvalidCurieError(f"Invalid input curie id: {curie}")
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
