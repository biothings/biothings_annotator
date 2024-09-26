"""
Exercises the query methods within the biothings_annotator package
"""

import logging
import random
from typing import Dict, List

import biothings_client
import pytest

from biothings_annotator import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings, utils
from biothings_annotator.annotator.settings import SERVICE_PROVIDER_API_HOST

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.unit
@pytest.mark.parametrize("node_type", ["gene", "chem", "disease", "phenotype", "NULL"])
def test_annotation_client(node_type: str):
    """
    Tests accessing different flavors of the biothings client from within the scope of the annotator
    instance

    If a valid keyword for the node is provided, then we'll yield an instance of the
    biothings_client for accessing nodes of that type

    Otherwise we raise a KeyError attempting to access a node type that doesn't exist for the
    biothings client
    """
    if node_type in ANNOTATOR_CLIENTS.keys():
        client = utils.get_client(node_type, SERVICE_PROVIDER_API_HOST)
        assert isinstance(client, biothings_client.BiothingClient)
    else:
        with pytest.raises(ValueError):
            utils.get_client(node_type, SERVICE_PROVIDER_API_HOST)


@pytest.mark.unit
@pytest.mark.parametrize("curie_prefix", list(BIOLINK_PREFIX_to_BioThings.keys()))
def test_biothings_query(curie_prefix: str):
    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    node_type, node_id = utils.parse_curie(curie=curie_query, return_type=True, return_id=True)

    domain_fields = ANNOTATOR_CLIENTS[node_type]["fields"]
    client = utils.get_client(node_type, SERVICE_PROVIDER_API_HOST)
    if not client:
        logger.warning("Failed to get the biothings client for %s type. This type is skipped.", node_type)
        return {}

    fields = ANNOTATOR_CLIENTS[node_type]["fields"]
    scopes = ANNOTATOR_CLIENTS[node_type]["scopes"]
    querymany_result = client.querymany([node_id], scopes=scopes, fields=fields)
    logger.info("Done. %s annotation objects returned.", len(querymany_result))
    query_response = utils.group_by_subfield(collection=querymany_result, search_key="query")

    assert isinstance(query_response, dict)
    logger.info((f"Query Response: {query_response}" f"Query Fields: {domain_fields}"))


@pytest.mark.unit
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
def test_query_post_processing(search_keyword: str, collection: List[Dict], histogram: Dict):
    """
    Evaluates the group_by_subfield helper function for creating a dictionary histrogram of the
    based off the aggregated collection of dictionaries sharing a common key.

    Parameterized tests
    1) single-length entry
    2) multi-length entry
    3) search key not found
    4) empty collection (1)
    5) empty collection (2)
    6) empty collection and empty search key
    """
    histogram_response = utils.group_by_subfield(collection=collection, search_key=search_keyword)
    assert isinstance(histogram_response, dict)
    assert histogram_response == histogram
