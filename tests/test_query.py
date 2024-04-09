"""
Exercises the query methods within the biothings_annotator package
"""

import logging
import itertools
import random

import pytest

import biothings_client

from biothings_annotator import Annotator, BIOLINK_PREFIX_to_BioThings


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.parametrize("node_type, client_type", ["gene", "chem", "disease", "phenotype", "NULL"])
def test_annotation_client(node_type: str):
    """
    Tests accessing different flavors of the biothings client from within the scope of the annotator
    instance

    If a valid keyword for the node is provided, then we'll yield an instance of the
    biothings_client for accessing nodes of that type

    Otherwise we raise a ValueError attempting to access a node type that doesn't exist for the
    biothings client
    """
    annotation_instance = Annotator()
    if node_type in annotation_instance.annotator_clients.keys():
        client = annotation_instance.get_client(node_type)
        assert isinstance(client, biothings_client.BiothingClient)
    else:
        with pytest.raises(ValueError):
            annotation_instance.get_client(node_type)


@pytest.mark.parametrize("curie_prefix", list(BIOLINK_PREFIX_to_BioThings.keys()))
def test_biothings_query(curie_prefix: str):
    annotation_instance = Annotator()

    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    node_type, node_id = annotation_instance.parse_curie(curie=curie_query, return_type=True, return_id=True)

    domain_fields = annotation_instance.annotator_clients[node_type]["fields"]
    # for field_combination in itertools.chain.from_iterable(
    #     itertools.combinations(domain_fields, sub_fields) for sub_fields in range(len(domain_fields) + 1)
    # ):
    # query_response = annotation_instance.query_biothings(
    #     node_type=node_type, query_list=[node_id], fields=domain_fields
    # )

    client = annotation_instance.get_client(node_type)
    if not client:
        logger.warning("Failed to get the biothings client for %s type. This type is skipped.", node_type)
        return {}
    fields = annotation_instance.annotator_clients[node_type]["fields"]
    scopes = annotation_instance.annotator_clients[node_type]["scopes"]
    # logger.info("Querying annotations for %s %ss...", len(query_list), node_type)
    res = client.querymany([node_id], scopes=scopes, fields=fields)
    import json
    import copy

    with open(f"{node_type}_{curie_query}.json", "w", encoding="utf-8") as handle:
        local_scope = copy.copy(locals())
        local_scope.pop("annotation_instance")
        local_scope.pop("json")
        local_scope.pop("copy")
        local_scope.pop("handle")
        local_scope.pop("client")
        handle.write(json.dumps(local_scope, indent=4))
    logger.info("Done. %s annotation objects returned.", len(res))
    structured_response = annotation_instance._map_group_query_subfields(collection=res, search_key="query")
    # return structured_response

    # assert isinstance(query_response, dict)
    # logger.info((f"Query Response: {query_response}" f"Query Fields: {domain_fields}"))


@pytest.mark.parametrize(
    "search_keyword, collection, histogram",
    [
        (
            "entry",
            [{"entry": "compilation", "status": "NORMAL", "_id": 82}],
            {"compilation": [{"entry": "compilation", "status": "NORMAL", "_id": 82}]},
        ),
        (
            "entry",
            [
                {"entry": "linker", "status": "NORMAL", "_id": 23},
                {"entry": "builder", "status": "WARNING", "_id": 3},
                {"entry": "builder", "status": "WARNING", "_id": 8},
                {"entry": "builder", "status": "NORMAL", "_id": 92},
                {"entry": "compilation", "status": "WARNING", "_id": 55},
                {"entry": "compilation", "status": "NORMAL", "_id": 80},
                {"entry": "runtime", "status": "NORMAL", "_id": 80},
                {"entry": "runtime", "status": "WARNING", "_id": 83},
                {"entry": "runtime", "status": "ERROR", "_id": 99},
                {"entry": "cleanup", "status": "NORMAL", "_id": 1},
                {"entry": "cleanup", "status": "NORMAL", "_id": 10},
            ],
            {
                "linker": [{"entry": "linker", "status": "NORMAL", "_id": 23}],
                "builder": [
                    {"entry": "builder", "status": "WARNING", "_id": 3},
                    {"entry": "builder", "status": "WARNING", "_id": 8},
                    {"entry": "builder", "status": "NORMAL", "_id": 92},
                ],
                "compilation": [
                    {"entry": "compilation", "status": "WARNING", "_id": 55},
                    {"entry": "compilation", "status": "NORMAL", "_id": 80},
                ],
                "runtime": [
                    {"entry": "runtime", "status": "NORMAL", "_id": 80},
                    {"entry": "runtime", "status": "WARNING", "_id": 83},
                    {"entry": "runtime", "status": "ERROR", "_id": 99},
                ],
                "cleanup": [
                    {"entry": "cleanup", "status": "NORMAL", "_id": 1},
                    {"entry": "cleanup", "status": "NORMAL", "_id": 10},
                ],
            },
        ),
        ("NULL", [{"entry": "compilation", "status": "NORMAL", "_id": 82}], {}),
        ("NULL", [{}], {}),
        ("NULL", [], {}),
        ("", [{}], {}),
    ],
)
def test_query_post_processing(search_keyword: str, collection: list[dict], histogram: dict):
    """
    Evaluates the _map_group_query_subfields method for creating a dictionary histrogram of the
    based off the aggregated collection of dictionaries sharing a common key.

    Parameterized tests
    1) single-length entry
    2) multi-length entry
    3) search key not found
    4) empty collection (1)
    5) empty collection (2)
    6) empty collection and empty search key
    """
    annotation_instance = Annotator()
    histogram_response = annotation_instance._map_group_query_subfields(
        collection=collection, search_key=search_keyword
    )
    assert isinstance(histogram_response, dict)
    assert histogram_response == histogram
