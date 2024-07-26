"""
Translator Node Annotator Service Handler
"""

import logging

from .exceptions import InvalidCurieError, TRAPIInputError
from .settings import ANNOTATOR_CLIENTS
from .transformer import ResponseTransformer
from .utils import get_client, get_dotfield_value, parse_curie

logger = logging.getLogger(__name__)


class Annotator:

    def query_biothings(self, node_type: str, query_list, fields=None) -> dict:
        """
        Query biothings client based on node_type for a list of ids
        """
        client = get_client(node_type)
        if not client:
            logger.warning("Failed to get the biothings client for %s type. This type is skipped.", node_type)
            return {}
        fields = fields or ANNOTATOR_CLIENTS[node_type]["fields"]
        scopes = ANNOTATOR_CLIENTS[node_type]["scopes"]
        logger.info("Querying annotations for %s %ss...", len(query_list), node_type)
        res = client.querymany(query_list, scopes=scopes, fields=fields)
        logger.info("Done. %s annotation objects returned.", len(res))
        structured_response = self._map_group_query_subfields(collection=res, search_key="query")
        return structured_response

    def _map_group_query_subfields(self, collection: list[dict], search_key: str) -> dict:
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

    def annotate_curie(self, curie: str, raw: bool = False, fields=None):
        """
        Annotate a single curie id
        """
        node_type, _id = parse_curie(curie)
        if not node_type:
            raise InvalidCurieError(f"Unsupported Curie prefix: {curie}")
        res = self.query_biothings(node_type, [_id], fields=fields)
        if not raw:
            res = self.transform(res, node_type)
            # res = [self.transform(r) for r in res[_id]]
        return {curie: res.get(_id, {})}

    def transform(self, res_by_id, node_type):
        """
        perform any transformation on the annotation object, but in-place also returned object
        res_by_id is the output of query_biothings, node_type is the same passed to query_biothings
        """
        logger.info("Transforming output annotations for %s %ss...", len(res_by_id), node_type)
        transformer = ResponseTransformer(res_by_id, node_type)
        transformer.transform()
        logger.info("Done.")
        ####
        # if isinstance(res, list):
        #     # TODO: handle multiple results here
        #     res = [transformer.transform(r) for r in res]
        # else:
        #     res.pop("query", None)
        #     res.pop("_score", None)
        #     res = transformer.transform(res)
        ####
        return res_by_id

    def annotate_trapi(
        self, trapi_input: dict, append: bool = False, raw: bool = False, fields: list = None, limit: int = None
    ):
        """
        Annotate a TRAPI input message with node annotator annotations
        """
        try:
            node_d = get_dotfield_value("message.knowledge_graph.nodes", trapi_input)
            assert isinstance(node_d, dict)
        except (KeyError, ValueError, AssertionError):
            raise TRAPIInputError("Invalid input format")

        # if limit is set, we truncate the node_d to that size
        if limit:
            _node_d = {}
            i = 0
            for node_id in node_d:
                i += 1
                if i > limit:
                    break
                _node_d[node_id] = node_d[node_id]
            node_d = _node_d
            del i, _node_d

        node_list_by_type = {}
        for node_id in node_d:
            node_type = parse_curie(node_id, return_type=True, return_id=False)
            if node_type:
                if node_type not in node_list_by_type:
                    node_list_by_type[node_type] = [node_id]
                else:
                    node_list_by_type[node_type].append(node_id)
            else:
                logger.warning("Unsupported Curie prefix: %s. Skipped!", node_id)

        for node_type, node_list in node_list_by_type.items():
            if node_type not in ANNOTATOR_CLIENTS or not node_list_by_type[node_type]:
                # skip for now
                continue

            # this is the list of original node ids like NCBIGene:1017, should be a unique list
            node_list = node_list_by_type[node_type]

            # this is the list of query ids like 1017
            query_list = [
                parse_curie(_id, return_type=False, return_id=True) for _id in node_list_by_type[node_type]
            ]
            # query_id to original id mapping
            node_id_d = dict(zip(query_list, node_list))
            res_by_id = self.query_biothings(node_type, query_list, fields=fields)
            if not raw:
                res_by_id = self.transform(res_by_id, node_type)
            for node_id in res_by_id:
                orig_node_id = node_id_d[node_id]
                res = res_by_id[node_id]
                # if not raw:
                #     if isinstance(res, list):
                #         # TODO: handle multiple results here
                #         res = [self.transform(r) for r in res]
                #     else:
                #         res = self.transform(res)
                res = {
                    "attribute_type_id": "biothings_annotations",
                    "value": res,
                }
                if append:
                    # append annotations to existing "attributes" field
                    node_d[orig_node_id]["attributes"].append(res)
                else:
                    # return annotations only
                    node_d[orig_node_id]["attributes"] = [res]

        return node_d
