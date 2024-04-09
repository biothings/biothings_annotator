"""
Exercises the transformer instance
"""

import logging
import itertools
import random

import pytest

from biothings_annotator import Annotator, BIOLINK_PREFIX_to_BioThings, ResponseTransformer

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.parametrize("curie_prefix", list(BIOLINK_PREFIX_to_BioThings.keys()))
def test_annotation_transform(curie_prefix: str):
    annotation_instance = Annotator()

    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    node_type, node_id = annotation_instance.parse_curie(curie=curie_query, return_type=True, return_id=True)

    domain_fields = annotation_instance.annotator_clients[node_type]["fields"]
    query_response = annotation_instance.query_biothings(
        node_type=node_type, query_list=[node_id], fields=domain_fields
    )
    response_transformer = ResponseTransformer(res_by_id=query_response, node_type=node_type)
    assert response_transformer.res_by_id == query_response
    assert response_transformer.node_type == node_type
    assert response_transformer.data_cache == {}

    response_transformer.transform()
