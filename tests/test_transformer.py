"""
Exercises the transformer instance
"""

# pylint: disable=use-implicit-booleaness-not-comparison

import logging
import random

import pytest

from biothings_annotator import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings, Annotator, ResponseTransformer, utils
from biothings_annotator.annotator import transformer
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_chem_transform_does_not_load_atc_cache(monkeypatch):
    annotation_instance = Annotator()
    query_response = {"1017": [{"query": "1017", "_id": "1017", "symbol": "CDK2"}]}

    def fail_get_query_client(node_type, query_backend, api_host, elasticsearch_connection):
        raise AssertionError("non-chem transforms should not load extra ATC metadata")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        fail_get_query_client,
    )

    response = await annotation_instance.transform(query_response, node_type="gene")

    assert response == query_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chem_transform_continues_when_atc_cache_load_fails(monkeypatch):
    annotation_instance = Annotator()
    query_response = {
        "CHEMBL123": [
            {
                "query": "CHEMBL123",
                "_id": "CHEMBL123",
                "chembl": {
                    "drug_indications": [{"mesh_id": "D012345"}],
                    "atc_classifications": "A01AB02",
                },
            }
        ]
    }

    def fail_get_query_client(node_type, query_backend, api_host, elasticsearch_connection):
        raise RuntimeError("extra metadata unavailable")

    monkeypatch.setattr(
        "biothings_annotator.annotator.annotator.get_query_client",
        fail_get_query_client,
    )

    response = await annotation_instance.transform(query_response, node_type="chem")
    chembl_hit = response["CHEMBL123"][0]

    assert chembl_hit["chembl"]["drug_indications"] == [{"mesh_id": "MESH:D012345"}]
    assert "atc_classifications" not in chembl_hit


@pytest.mark.unit
@pytest.mark.asyncio
async def test_atc_cache_load_failure_does_not_cache_partial_results():
    cache_key = "test-atc-cache-load-failure"
    transformer.atc_cache.pop(cache_key, None)

    class FailingAtcClient:
        async def query(self, query, fields, fetch_all):
            async def results():
                yield {"atc": {"code": "A01", "name": "Stomatological preparations"}}
                raise RuntimeError("ATC stream failed")

            return results()

    with pytest.raises(RuntimeError):
        await transformer.load_atc_cache(
            SERVICE_PROVIDER_API_HOST,
            atc_client=FailingAtcClient(),
            cache_key=cache_key,
        )

    assert cache_key not in transformer.atc_cache
