"""
Translator Node Annotator Service Handler
"""

from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Tuple, Union
import logging
import os

import biothings_client

from biothings_annotator.annotator.exceptions import InvalidCurieError, InvalidQueryBackendError, TRAPIInputError
from biothings_annotator.annotator.settings import (
    ANNOTATOR_CLIENTS,
    BIOLINK_PREFIX_to_BioThings,
    ELASTICSEARCH_CONNECTION,
    QUERY_BACKEND,
    QUERY_BACKEND_ALIASES,
    QUERY_BACKEND_ENV,
    SERVICE_PROVIDER_API_HOST,
    SUPPORTED_QUERY_BACKENDS,
)
from biothings_annotator.annotator.transformer import ResponseTransformer, load_atc_cache
from biothings_annotator.annotator.utils import (
    batched,
    get_client,
    get_dotfield_value,
    get_query_client,
    group_by_subfield,
    parse_curie,
)

logger = logging.getLogger(__name__)


class Annotator:
    def __init__(self, query_backend: Optional[str] = None):
        self.api_host = os.environ.get("SERVICE_PROVIDER_API_HOST", SERVICE_PROVIDER_API_HOST)
        deployment_backend = self._normalize_query_backend(os.environ.get(QUERY_BACKEND_ENV, QUERY_BACKEND))
        if query_backend is None:
            self.query_backend = deployment_backend
        else:
            try:
                self.query_backend = self._normalize_query_backend(query_backend)
            except InvalidQueryBackendError:
                self.query_backend = deployment_backend
        self.elasticsearch_connection = os.environ.get("ELASTICSEARCH_CONNECTION", ELASTICSEARCH_CONNECTION).strip()

    @staticmethod
    def _normalize_query_backend(query_backend: str) -> str:
        try:
            normalized_backend = query_backend.strip().lower()
        except AttributeError as exc:
            raise InvalidQueryBackendError(query_backend) from exc

        normalized_backend = QUERY_BACKEND_ALIASES.get(normalized_backend, normalized_backend)
        if normalized_backend not in SUPPORTED_QUERY_BACKENDS:
            raise InvalidQueryBackendError(query_backend)
        return normalized_backend

    @property
    def atc_cache_key(self) -> str:
        if self.query_backend == "elasticsearch":
            return f"{self.query_backend}:{self.elasticsearch_connection}"
        return f"{self.query_backend}:{self.api_host}"

    def _default_scopes(self, node_type: str) -> Union[str, List[str]]:
        """Return the backend-appropriate default query scopes for a node type."""
        client_settings = ANNOTATOR_CLIENTS[node_type]
        if self.query_backend == "elasticsearch":
            return client_settings.get("elasticsearch_scopes", client_settings["scopes"])
        return client_settings["scopes"]

    def _scopes_for_prefix(self, node_type: str, prefix: str) -> Union[str, List[str]]:
        """Return prefix-specific scopes using exact ES fields when configured."""
        prefix_settings = BIOLINK_PREFIX_to_BioThings.get(prefix, {})
        if self.query_backend == "elasticsearch":
            elasticsearch_scopes = prefix_settings.get("elasticsearch_scopes")
            if elasticsearch_scopes:
                return elasticsearch_scopes
        return prefix_settings.get("scopes") or self._default_scopes(node_type)

    async def query_biothings(
        self, node_type: str, query_list: List[str], fields: Optional[Union[str, List[str]]] = None
    ) -> Dict:
        """
        Query biothings client based on node_type for a list of ids
        """
        client = get_client(node_type, self.api_host)
        if not isinstance(client, biothings_client.AsyncBiothingClient):
            logger.error("Failed to get the biothings client for %s type. This type is skipped.", node_type)
            return {}

        fields = fields or ANNOTATOR_CLIENTS[node_type]["fields"]
        scopes = ANNOTATOR_CLIENTS[node_type]["scopes"]
        logger.info("Querying annotations for %s %ss...", len(query_list), node_type)
        res = await client.querymany(query_list, scopes=scopes, fields=fields)
        logger.info("Done. %s annotation objects returned.", len(res))
        grouped_response = group_by_subfield(collection=res, search_key="query")
        return grouped_response

    async def query_annotations(
        self,
        node_type: str,
        query_list: List[str],
        fields: Optional[Union[str, List[str]]] = None,
        scopes: Optional[Union[str, List[str]]] = None,
    ) -> Dict:
        """
        Query annotations through the configured backend.

        scopes defaults to the backend-appropriate full scope list, but callers that
        know the originating BIOLINK prefix should pass its narrower per-prefix scopes
        (see BIOLINK_PREFIX_to_BioThings) instead.
        """
        client = get_query_client(
            node_type=node_type,
            query_backend=self.query_backend,
            api_host=self.api_host,
            elasticsearch_connection=self.elasticsearch_connection,
        )
        if client is None or not hasattr(client, "querymany"):
            logger.error("Failed to get the annotation query client for %s type. This type is skipped.", node_type)
            return {}

        query_list = list(query_list)
        fields = fields or ANNOTATOR_CLIENTS[node_type].get("fields", "all")
        scopes = scopes or self._default_scopes(node_type)
        logger.info("Querying %s annotations for %s %ss...", self.query_backend, len(query_list), node_type)
        res = await client.querymany(query_list, scopes=scopes, fields=fields)
        logger.info("Done. %s %s annotation objects returned.", len(res), self.query_backend)
        grouped_response = group_by_subfield(collection=res, search_key="query")
        return grouped_response

    async def transform(self, res_by_id: Dict, node_type: str):
        """
        perform any transformation on the annotation object, but in-place also returned object
        res_by_id is the output of query_annotations, node_type is the same passed to query_annotations
        """
        logger.info("Transforming output annotations for %s %ss...", len(res_by_id), node_type)
        atc_cache = {}
        if node_type == "chem":
            try:
                atc_client = get_query_client(
                    node_type="extra",
                    query_backend=self.query_backend,
                    api_host=self.api_host,
                    elasticsearch_connection=self.elasticsearch_connection,
                )
                if atc_client is None or not hasattr(atc_client, "query"):
                    logger.warning("Failed to get the extra annotation query client. ATC enrichment is skipped.")
                else:
                    atc_cache = await load_atc_cache(self.api_host, atc_client=atc_client, cache_key=self.atc_cache_key)
            except Exception as exc:
                logger.warning("Unable to load WHO ATC code-to-name mapping; skipping ATC enrichment: %r", exc)
        transformer = ResponseTransformer(res_by_id, node_type, self.api_host, atc_cache)
        transformer.transform()
        logger.info("Done.")
        return res_by_id

    async def append_extra_annotations(
        self, node_d: Dict, node_id_subset: Optional[List[str]] = None, batch_n: int = 1000
    ):
        """
        Append extra annotations to the existing node_d
        """
        node_id_list = list(node_d.keys() if node_id_subset is None else node_id_subset)
        if not node_id_list:
            logger.info("No extra annotations requested.")
            return

        cnt = 0
        logger.info("Retrieving extra annotations...")
        try:
            extra_api = get_query_client(
                node_type="extra",
                query_backend=self.query_backend,
                api_host=self.api_host,
                elasticsearch_connection=self.elasticsearch_connection,
            )
        except Exception as exc:
            logger.warning("Unable to get the extra annotation query client. Extra annotations are skipped: %r", exc)
            return
        if extra_api is None or not hasattr(extra_api, "querymany"):
            logger.warning("Failed to get the extra annotation query client. Extra annotations are skipped.")
            return

        for node_id_batch in batched(node_id_list, batch_n):
            try:
                extra_res = await extra_api.querymany(node_id_batch, scopes="_id", fields="all")
            except Exception as exc:
                logger.warning("Unable to retrieve extra annotations. Extra annotations are skipped: %r", exc)
                return
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

    async def annotate_curie(
        self, curie: str, raw: bool = False, fields: Optional[Union[str, List[str]]] = None, include_extra: bool = True
    ) -> Dict:
        """
        Annotate a single curie id
        """
        node_type, _id = parse_curie(curie)
        if not node_type:
            raise InvalidCurieError(curie)

        prefix = curie.split(":", 1)[0]
        scopes = self._scopes_for_prefix(node_type, prefix)
        res = await self.query_annotations(node_type, [_id], fields=fields, scopes=scopes)

        if not raw:
            res = await self.transform(res, node_type)

        if res and include_extra and node_type == "chem":
            await self.append_extra_annotations(res)

        curie_annotation = {curie: res.get(_id, {})}
        return curie_annotation

    def _group_curies_by_scopes(
        self, node_type: str, node_list: List[str]
    ) -> List[Tuple[Union[str, List[str]], List[str]]]:
        """
        Group curies of the same node_type by their backend-appropriate querymany
        scopes. Prefix-specific groups prevent incompatible identifiers from being
        queried against fields such as the numeric Elasticsearch "retired" field.
        """
        groups: "OrderedDict[Tuple, List[str]]" = OrderedDict()
        scopes_by_key: Dict[Tuple, Union[str, List[str]]] = {}
        for curie in node_list:
            prefix = curie.split(":", 1)[0]
            scopes = self._scopes_for_prefix(node_type, prefix)
            key = tuple(scopes) if isinstance(scopes, list) else scopes
            groups.setdefault(key, []).append(curie)
            scopes_by_key[key] = scopes
        return [(scopes_by_key[key], curies) for key, curies in groups.items()]

    async def _annotate_node_list_by_type(
        self, node_list_by_type: Dict, raw: bool = False, fields: Optional[Union[str, List[str]]] = None
    ) -> Iterable[tuple]:
        """
        This is a helper method re-used in both annotate_curie_list and annotate_trapi methods
        It returns a generator of tuples of (original_node_id, annotation_object) for each node_id,
        passed via node_list_by_type.
        """
        for node_type, node_list in node_list_by_type.items():
            if node_type not in ANNOTATOR_CLIENTS or not node_list_by_type[node_type]:
                # skip for now
                continue

            # this is the list of original node ids like NCBIGene:1017, should be a unique list
            node_list = node_list_by_type[node_type]

            for scopes, scoped_node_list in self._group_curies_by_scopes(node_type, node_list):
                # this is the list of query ids like 1017
                query_list = [parse_curie(_id, return_type=False, return_id=True) for _id in scoped_node_list]

                # query_id to original id mapping
                node_id_d = dict(zip(query_list, scoped_node_list))
                res_by_id = await self.query_annotations(node_type, query_list, fields=fields, scopes=scopes)
                if not raw:
                    res_by_id = await self.transform(res_by_id, node_type)

                # map back to original node ids
                # NOTE: we don't want to use `for node_id in res_by_id:` here, since we will mofiify res_by_id in the loop
                for node_id in list(res_by_id.keys()):
                    orig_node_id = node_id_d[node_id]
                    if node_id != orig_node_id:
                        res_by_id[orig_node_id] = res_by_id.pop(node_id)
                    yield (orig_node_id, res_by_id[orig_node_id])

    async def annotate_curie_list(
        self,
        curie_list: Union[List[str], Iterable[str]],
        raw: bool = False,
        fields: Optional[Union[str, List[str]]] = None,
        include_extra: bool = True,
    ) -> Union[Dict, Iterable[tuple]]:
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

        async for node_id, res in self._annotate_node_list_by_type(node_list_by_type, raw=raw, fields=fields):
            node_d[node_id] = res

        if include_extra:
            # currently, we only need to append extra annotations for chem nodes
            await self.append_extra_annotations(node_d, node_id_subset=node_list_by_type.get("chem", []))
        return node_d

    async def annotate_trapi(
        self,
        trapi_input: Dict,
        append: bool = False,
        raw: bool = False,
        fields: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        include_extra: bool = True,
    ) -> Dict:
        """
        Annotate a TRAPI input message with node annotator annotations
        """
        try:
            node_d = get_dotfield_value("message.knowledge_graph.nodes", trapi_input)
            assert isinstance(node_d, dict)
        except (KeyError, ValueError, AssertionError) as access_error:
            raise TRAPIInputError(trapi_input) from access_error

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
        async for node_id, res in self._annotate_node_list_by_type(node_list_by_type, raw=raw, fields=fields):
            _node_d[node_id] = res

        if include_extra:
            # currently, we only need to append extra annotations for chem nodes
            await self.append_extra_annotations(_node_d, node_id_subset=node_list_by_type.get("chem", []))

        # place the annotation objects back to the original node_d as TRAPI attributes
        for node_id, res in _node_d.items():
            res = {
                "attribute_type_id": "biothings_annotations",
                "value": res,
            }

            node_attributes = node_d[node_id].get("attributes", None)
            if node_attributes is None:
                node_d[node_id]["attributes"] = []

            if append:
                # append annotations to existing "attributes" field
                node_d[node_id]["attributes"].append(res)
            else:
                # return annotations only
                node_d[node_id]["attributes"] = [res]

        return node_d
