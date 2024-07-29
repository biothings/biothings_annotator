"""
Exercises the transformer instance
"""

import logging
import random

import pytest

from biothings_annotator import ANNOTATOR_CLIENTS, Annotator, BIOLINK_PREFIX_to_BioThings, ResponseTransformer, utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.parametrize("curie_prefix", list(BIOLINK_PREFIX_to_BioThings.keys()))
def test_annotation_transform(curie_prefix: str):
    annotation_instance = Annotator()

    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    node_type, node_id = utils.parse_curie(curie=curie_query, return_type=True, return_id=True)

    domain_fields = ANNOTATOR_CLIENTS[node_type]["fields"]
    query_response = annotation_instance.query_biothings(
        node_type=node_type, query_list=[node_id], fields=domain_fields
    )
    response_transformer = ResponseTransformer(res_by_id=query_response, node_type=node_type)
    assert response_transformer.res_by_id == query_response
    assert response_transformer.node_type == node_type
    assert response_transformer.data_cache == {}

    response_transformer.transform()
    assert response_transformer.res_by_id == query_response
    assert response_transformer.node_type == node_type
    assert response_transformer.data_cache == {}

    response_transformer.transform()
