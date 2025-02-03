"""
Exercises the transformer instance
"""

# pylint: disable=use-implicit-booleaness-not-comparison

import logging
import random

import pytest

from biothings_annotator import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings, Annotator, ResponseTransformer, utils
from biothings_annotator.annotator.settings import SERVICE_PROVIDER_API_HOST

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("curie_prefix", list(BIOLINK_PREFIX_to_BioThings.keys()))
async def test_annotation_transform(curie_prefix: str):
    annotation_instance = Annotator()

    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    node_type, node_id = utils.parse_curie(curie=curie_query, return_type=True, return_id=True)

    domain_fields = ANNOTATOR_CLIENTS[node_type]["fields"]
    query_response = await annotation_instance.query_biothings(
        node_type=node_type, query_list=[node_id], fields=domain_fields
    )

    api_host = SERVICE_PROVIDER_API_HOST
    atc_cache = {}
    response_transformer = ResponseTransformer(
        res_by_id=query_response, node_type=node_type, api_host=api_host, atc_cache=atc_cache
    )
    assert response_transformer.res_by_id == query_response
    assert response_transformer.node_type == node_type
    assert response_transformer.data_cache == {}  # explicit empty dict

    response_transformer.transform()
    assert response_transformer.res_by_id == query_response
    assert response_transformer.node_type == node_type
    assert response_transformer.data_cache == {}  # explicit empty dict

    response_transformer.transform()
