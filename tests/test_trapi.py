"""
Tests the TRAPI request parsing capability for the biothings annotation package
"""

import logging

import pytest

from biothings_annotator import Annotator, utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class TestTrapiAnnotation:
    """
    Responses should have the following structure
      "PUBCHEM.COMPOUND:9961741":
      {
        "attributes": [
          {
            "attribute_type_id": "biothings_annotations",
            "value": [
              {
                "query": "9961741",
                "_id": "VHVPQPYKVGDNFY-DKYCYSLVSA-N",
                "_score": 17.100336,
                "chembl": {
                  "_license": "http://bit.ly/2KAUCAm",
                  "first_in_class": -1,
                  "inorganic_flag": -1,
                  "molecule_chembl_id": "CHEMBL454471",
                  "molecule_type": "Small molecule",
                  "prodrug": -1,
                  "smiles": "CC[C@@H](C)n1ncn(-c2ccc(N3CCN(c4ccc(OC[C@@H]5CO[C@@](Cn6cncn6)(c6ccc(Cl)cc6Cl)O5)cc4)CC3)cc2)c1=O",
                  "structure_type": "MOL",
                  "therapeutic_flag": false
                },
                "pubchem": {
                  "_license": "http://bit.ly/2AqoLOc",
                  "cid": 9961741,
                  "inchi": "InChI=1S/C35H38Cl2N8O4/c1-3-25(2)45-34(46)44(24-40-45)29-7-5-27(6-8-29)41-14-16-42(17-15-41)28-9-11-30(12-10-28)47-19-31-20-48-35(49-31,21-43-23-38-22-39-43)32-13-4-26(36)18-33(32)37/h4-13,18,22-25,31H,3,14-17,19-21H2,1-2H3/t25-,31-,35-/m1/s1",
                  "inchikey": "VHVPQPYKVGDNFY-DKYCYSLVSA-N",
                  "molecular_formula": "C35H38Cl2N8O4",
                  "molecular_weight": 705.6
                },
                "unii": {
                  "_license": "http://bit.ly/2Pg8Oo9",
                  "unii": "6B8556A65Q"
                }
              }
            ]
          }
        ]
      }
    """

    annotation_instance = Annotator()

    @pytest.mark.parametrize("data_store", [["trapi_request.json"]], indirect=True)
    def test_default(self, data_store: dict):
        """
        Tests the TRAPI annotation method with default arguments
        """
        append = False
        raw = False
        fields = None
        limit = None

        annotation = self.annotation_instance.annotate_trapi(
            trapi_input=data_store, append=append, raw=raw, fields=fields, limit=limit
        )
        node_set = set(data_store["message"]["knowledge_graph"]["nodes"].keys())
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
                            del curie_prefix
                            assert values == {"query": query, "notfound": True}
                        else:
                            assert isinstance(values, dict)
                            query = values.get("query", None)
                            assert query is not None
                            identifier = values.get("_id", None)
                            assert identifier is not None
                            score = values.get("_score", None)
                            assert score is not None

    @pytest.mark.parametrize("data_store", [["trapi_request.json"]], indirect=True)
    def test_append(self, data_store: dict):
        """
        Tests the TRAPI annotation method with append enabled
        """
        append = True
        raw = False
        fields = None
        limit = None

        annotation = self.annotation_instance.annotate_trapi(
            trapi_input=data_store, append=append, raw=raw, fields=fields, limit=limit
        )
        node_set = set(data_store["message"]["knowledge_graph"]["nodes"].keys())
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

    @pytest.mark.parametrize("data_store", [["trapi_request.json"]], indirect=True)
    def test_raw(self, data_store: dict):
        """
        Tests the TRAPI annotation method with raw enabled
        """
        append = False
        raw = True
        fields = None
        limit = None

        annotation = self.annotation_instance.annotate_trapi(
            trapi_input=data_store, append=append, raw=raw, fields=fields, limit=limit
        )
        node_set = set(data_store["message"]["knowledge_graph"]["nodes"].keys())
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

    @pytest.mark.parametrize("data_store", [["trapi_request.json"]], indirect=True)
    def test_append_and_raw(self, data_store: dict):
        """
        Tests the TRAPI annotation method with append & raw enabled
        """
        append = True
        raw = True
        fields = None
        limit = None

        annotation = self.annotation_instance.annotate_trapi(
            trapi_input=data_store, append=append, raw=raw, fields=fields, limit=limit
        )
        node_set = set(data_store["message"]["knowledge_graph"]["nodes"].keys())
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
                            del curie_prefix
                            assert values == {"query": query, "notfound": True}
                        else:
                            assert isinstance(values, dict)
                            query = values.get("query", None)
                            assert query is not None
                            identifier = values.get("_id", None)
                            assert identifier is not None
                            score = values.get("_score", None)
                            assert score is not None
