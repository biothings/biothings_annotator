"""
Tests the CURIE parsing capability for the biothings annotation package
"""

import logging
import random

import pytest

from biothings_annotator import BIOLINK_PREFIX_to_BioThings, utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.unit
@pytest.mark.parametrize("curie_prefix", list(BIOLINK_PREFIX_to_BioThings.keys()))
def test_curie_parsing(curie_prefix: str):
    """
    Tests the CURIE prefix parsing capability
    https://www.w3.org/TR/curie/#sec_2.1

    In reality we mainly target the following format:
    <prefix>:<id>
    """

    random_index = random.randint(0, 10000)
    curie_query = f"{curie_prefix}:{str(random_index)}"

    parsed_result = utils.parse_curie(curie=curie_query, return_type=True, return_id=True)
    parsed_type = utils.parse_curie(curie=curie_query, return_type=True, return_id=False)
    parsed_id = utils.parse_curie(curie=curie_query, return_type=False, return_id=True)
    parsed_null = utils.parse_curie(curie=curie_query, return_type=False, return_id=False)
    static_prefix = BIOLINK_PREFIX_to_BioThings[curie_prefix].get("keep_prefix", False)
    assert parsed_result[0] == BIOLINK_PREFIX_to_BioThings[curie_prefix]["type"]

    if static_prefix:
        assert parsed_result[1] == curie_query
    else:
        assert parsed_result[1] == str(random_index)

    assert parsed_result[0] == parsed_type
    assert parsed_result[1] == parsed_id
    assert parsed_null is None
    logger.info(f"Query: {curie_query} | Parsed Type: {parsed_type} | Parsed ID: {parsed_id}")


@pytest.mark.unit
@pytest.mark.parametrize(
    "encoded_curie,decoded_curie",
    [
        ("NCBIGene%3A1017", "NCBIGene:1017"),
        ("UMLS%3A8294", "UMLS:8294"),
        ("MESH%3A1192", "MESH:1192"),
    ],
)
def test_curie_decode_parsing(encoded_curie: str, decoded_curie: str):
    """
    Due to the swagger API frontend, we have to ensure that our GET endpoint
    can properly decode the reserved character `:`

    See the following reference for more information on reserved characters:
    https://www.rfc-editor.org/rfc/rfc1738
    """
    breakpoint()
    parsed_result = utils.parse_curie(curie=encoded_curie, return_type=True, return_id=True)
