import pytest
import sanic

from biothings_annotator import utils


@pytest.mark.parametrize("endpoint", ["/", "/annotator/", "/curie/"])
def test_curie_get(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the CURIE endpoint GET
    """
    curie_id = "NCBIGene:1017"
    url = f"{endpoint}{curie_id}"
    request, response = test_annotator.test_client.request(url, http_method="get")

    assert request.method == "GET"
    assert request.is_safe
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == url

    expected_response_body = {
        "NCBIGene:1017": [
            {
                "query": "1017",
                "HGNC": "1771",
                "MIM": "116953",
                "_id": "1017",
                "_score": 26.198248,
                "alias": ["CDKN2", "p33(CDK2)"],
                "interpro": [
                    {"desc": "Protein kinase domain", "id": "IPR000719", "short_desc": "Prot_kinase_dom"},
                    {
                        "desc": "Serine/threonine-protein kinase, active site",
                        "id": "IPR008271",
                        "short_desc": "Ser/Thr_kinase_AS",
                    },
                    {
                        "desc": "Protein kinase-like domain superfamily",
                        "id": "IPR011009",
                        "short_desc": "Kinase-like_dom_sf",
                    },
                    {
                        "desc": "Protein kinase, ATP binding site",
                        "id": "IPR017441",
                        "short_desc": "Protein_kinase_ATP_BS",
                    },
                ],
                "name": "cyclin dependent kinase 2",
                "pharos": {
                    "target_id": 10687,
                    "tdl": "Tchem",
                },
                "summary": "This gene encodes a member of a family of serine/threonine protein kinases that participate in cell cycle regulation. The encoded protein is the catalytic subunit of the cyclin-dependent protein kinase complex, which regulates progression through the cell cycle. Activity of this protein is especially critical during the G1 to S phase transition. This protein associates with and regulated by other subunits of the complex including cyclin A or E, CDK inhibitor p21Cip1 (CDKN1A), and p27Kip1 (CDKN1B). Alternative splicing results in multiple transcript variants. [provided by RefSeq, Mar 2014].",
                "symbol": "CDK2",
                "taxid": 9606,
                "type_of_gene": "protein-coding",
            }
        ]
    }
    expected_response_body[curie_id][0].pop("_score")

    response_body = response.json
    response_body[curie_id][0].pop("_score")
    assert response.json == expected_response_body

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.parametrize("endpoint", ["/curie/"])
def test_curie_post(test_annotator: sanic.Sanic, endpoint: str):
    """
    Tests the CURIE endpoint GET
    """
    batch_curie = [
        "NCBIGene:695",
        "MONDO:0001222",
        "DOID:6034",
        "CHEMBL.COMPOUND:821",
        "PUBCHEM.COMPOUND:3406",
        "CHEBI:192712",
        "CHEMBL.COMPOUND:3707246",
    ]

    request, response = test_annotator.test_client.request(endpoint, http_method="post", json=batch_curie)

    assert request.method == "POST"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert isinstance(response.json, dict)
    assert set(response.json.keys()) == set(batch_curie)

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"


@pytest.mark.parametrize("endpoint", ["/", "/annotator/", "/trapi/"])
def test_trapi_post(test_annotator: sanic.Sanic, trapi_request: dict, endpoint: str):
    """
    Tests the POST endpoints for our annotation service
    """
    request, response = test_annotator.test_client.request(endpoint, http_method="post", json=trapi_request)

    assert request.method == "POST"
    assert request.query_string == ""
    assert request.scheme == "http"
    assert request.server_path == endpoint

    assert response.http_version == "HTTP/1.1"
    assert response.content_type == "application/json"
    assert response.is_success
    assert not response.is_error
    assert response.is_closed
    assert response.status_code == 200
    assert response.encoding == "utf-8"

    node_set = set(trapi_request["message"]["knowledge_graph"]["nodes"].keys())

    annotation = response.json
    assert isinstance(annotation, dict)
    for key, attribute in annotation.items():
        assert key in node_set
        if isinstance(attribute, dict):
            attribute = [attribute]
        assert isinstance(attribute, list)
        for subattribute in attribute:
            assert isinstance(subattribute, dict)
            subattribute_collection = subattribute.get("attributes", None)

            assert isinstance(subattribute_collection, list)
            for subattributes in subattribute_collection:
                assert subattributes["attribute_type_id"] == "biothings_annotations"
                assert isinstance(subattributes["value"], list)
                for values in subattributes["value"]:
                    notfound = values.get("notfound", False)
                    if notfound:
                        curie_prefix, query = utils.parse_curie(key)
                        assert values == {"query": query, "notfound": True}
                    else:
                        assert isinstance(values, dict)
                        query = values.get("query", None)
                        assert query is not None
                        identifier = values.get("_id", None)
                        assert identifier is not None
                        score = values.get("_score", None)
                        assert score is not None
