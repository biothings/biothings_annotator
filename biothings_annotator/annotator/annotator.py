"""
Translator Node Annotator Service Handler
"""

import logging
from collections import OrderedDict
from typing import Iterable, List, Optional, Union

from .exceptions import InvalidCurieError, TRAPIInputError
from .settings import ANNOTATOR_CLIENTS
from .transformer import ResponseTransformer
from .utils import batched, get_client, get_dotfield_value, group_by_subfield, parse_curie

logger = logging.getLogger(__name__)


class Annotator:

    def query_biothings(
        self, node_type: str, query_list: List[str], fields: Optional[Union[str, List[str]]] = None
    ) -> dict:
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
        grouped_response = group_by_subfield(collection=res, search_key="query")
        return grouped_response

    def transform(self, res_by_id, node_type):
        """
        perform any transformation on the annotation object, but in-place also returned object
        res_by_id is the output of query_biothings, node_type is the same passed to query_biothings
        """
        logger.info("Transforming output annotations for %s %ss...", len(res_by_id), node_type)
        transformer = ResponseTransformer(res_by_id, node_type)
        transformer.transform()
        logger.info("Done.")
        return res_by_id

    def append_extra_annotations(self, node_d: dict, node_id_subset: Optional[List[str]] = None, batch_n: int = 1000):
        """
        Append extra annotations to the existing node_d
        """
        node_id_list = node_d.keys() if node_id_subset is None else node_id_subset
        extra_api = get_client("extra")
        cnt = 0
        logger.info("Retrieving extra annotations...")
        for node_id_batch in batched(node_id_list, batch_n):
            extra_res = extra_api.querymany(node_id_batch, scopes="_id", fields="all")
            for hit in extra_res:
                if hit.get("notfound", False):
                    continue
                if hit and isinstance(hit, dict):
                    node_id = hit.pop("query", None)
                    if node_id and node_id in node_d:
                        hit.pop("_id", None)
                        hit.pop("_score", None)
                        _res = node_d[node_id]
                        if isinstance(_res, dict):
                            _res.update(hit)
                        elif isinstance(_res, list):
                            for _r in _res:
                                if isinstance(_r, dict):
                                    _r.update(hit)
                        else:
                            # should not happen
                            logger.error("Invalid node_d entry: %s (type: %s)", _res, type(_res))
                        cnt += 1
        logger.info("Done. %s extra annotations appended.", cnt)

    def annotate_curie(
        self, curie: str, raw: bool = False, fields: Optional[Union[str, List[str]]] = None, include_extra: bool = True
    ) -> dict:
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
        if res and include_extra:
            self.append_extra_annotations(res)
        return {curie: res.get(_id, {})}

    def _annotate_node_list_by_type(
        self, node_list_by_type: dict, raw: bool = False, fields: Optional[Union[str, List[str]]] = None
    ) -> Iterable[tuple]:
        """This is a helper method re-used in both annotate_curie_list and annotate_trapi methods
        It returns a generator of tuples of (original_node_id, annotation_object) for each node_id,
        passed via node_list_by_type.
        """
        for node_type, node_list in node_list_by_type.items():
            if node_type not in ANNOTATOR_CLIENTS or not node_list_by_type[node_type]:
                # skip for now
                continue

            # this is the list of original node ids like NCBIGene:1017, should be a unique list
            node_list = node_list_by_type[node_type]

            # this is the list of query ids like 1017
            query_list = [parse_curie(_id, return_type=False, return_id=True) for _id in node_list_by_type[node_type]]
            # query_id to original id mapping
            node_id_d = dict(zip(query_list, node_list))
            res_by_id = self.query_biothings(node_type, query_list, fields=fields)
            if not raw:
                res_by_id = self.transform(res_by_id, node_type)

            # map back to original node ids
            # NOTE: we don't want to use `for node_id in res_by_id:` here, since we will mofiify res_by_id in the loop
            for node_id in list(res_by_id.keys()):
                orig_node_id = node_id_d[node_id]
                if node_id != orig_node_id:
                    res_by_id[orig_node_id] = res_by_id.pop(node_id)
                yield (orig_node_id, res_by_id[orig_node_id])

    def annotate_curie_list(
        self,
        curie_list: Union[List[str], Iterable[str]],
        raw: bool = False,
        fields: Optional[Union[str, List[str]]] = None,
        include_extra: bool = True,
    ) -> Union[dict, Iterable[tuple]]:
        """
        Annotate a list of curie ids
        """
        node_list_by_type = {}
        node_d = OrderedDict()  # a dictionary to hold all annotations by each curie id
        for node_id in curie_list:
            node_d[node_id] = {}  # create a placeholder for each curie id
            node_type = parse_curie(node_id, return_type=True, return_id=False)
            if node_type:
                if node_type not in node_list_by_type:
                    node_list_by_type[node_type] = [node_id]
                else:
                    node_list_by_type[node_type].append(node_id)
            else:
                logger.warning("Unsupported Curie prefix: %s. Skipped!", node_id)

        for node_id, res in self._annotate_node_list_by_type(node_list_by_type, raw=raw, fields=fields):
            node_d[node_id] = res
        if include_extra:
            # currently, we only need to append extra annotations for chem nodes
            self.append_extra_annotations(node_d, node_id_subset=node_list_by_type.get("chem", []))
        return node_d

    def annotate_trapi(
        self,
        trapi_input: dict,
        append: bool = False,
        raw: bool = False,
        fields: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        include_extra: bool = True,
    ) -> dict:
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

        _node_d = {}
        for node_id, res in self._annotate_node_list_by_type(node_list_by_type, raw=raw, fields=fields):
            _node_d[node_id] = res

        if include_extra:
            # currently, we only need to append extra annotations for chem nodes
            self.append_extra_annotations(_node_d, node_id_subset=node_list_by_type["chem"])

        # place the annotation objects back to the original node_d as TRAPI attributes
        for node_id, res in _node_d.items():
            res = {
                "attribute_type_id": "biothings_annotations",
                "value": res,
            }
            if append:
                # append annotations to existing "attributes" field
                node_d[node_id]["attributes"].append(res)
            else:
                # return annotations only
                node_d[node_id]["attributes"] = [res]

        return node_d

    def annotate_trapi_0(
        self, trapi_input: dict, append: bool = False, raw: bool = False, fields: list = None, limit: int = None
    ):
        """
        Deprecated! Kept here for reference for now, pending to be deleted soon.
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
            query_list = [parse_curie(_id, return_type=False, return_id=True) for _id in node_list_by_type[node_type]]
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
