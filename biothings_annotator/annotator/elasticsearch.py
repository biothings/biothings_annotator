"""
Elasticsearch-backed query adapter for annotator data.
"""

import json
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Union

import httpx


class ElasticsearchAnnotatorClient:
    """
    Small async REST adapter that mirrors the BioThings methods used by the annotator.

    This is intentionally not a full BioThings SDK replacement. It supports the
    subset the annotator calls today:

    * querymany(query_list, scopes, fields=None, size=None)
    * query(query, fields=None, fetch_all=False, size=None, skip=0)

    Unsupported BioThings conveniences like species, facets, as_dataframe,
    return_raw, and returnall are intentionally absent so they fail explicitly
    instead of being ignored or partially emulated.
    """

    def __init__(
        self,
        host: str,
        index: str,
        query_size: int = 10,
        query_batch_size: int = 1000,
        timeout: Union[int, float] = 30,
        headers: Optional[Dict[str, str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.host = host.rstrip("/")
        self.index = index
        self.query_size = query_size
        if query_batch_size < 1:
            raise ValueError("query_batch_size must be at least 1")
        self.query_batch_size = query_batch_size
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.http_client = http_client

    async def querymany(
        self,
        query_list: Iterable[str],
        scopes: Union[str, List[str]],
        fields: Optional[Union[str, List[str]]] = None,
        size: Optional[int] = None,
    ) -> List[Dict]:
        """
        Query ES once per input ID and return BioThings-style hits with a query field.

        This mirrors the annotator's BioThings querymany usage: input terms are
        batched, each term returns up to size hits, and results are flattened
        into one list. BioThings querymany extras such as returnall,
        as_dataframe, and return_raw are not implemented.
        """
        query_list = list(query_list)
        if not query_list:
            return []

        query_size = self.query_size if size is None else size
        results = []
        for query_batch in self._iter_batches(query_list, self.query_batch_size):
            results.extend(await self._querymany_batch(query_batch, scopes=scopes, fields=fields, size=query_size))

        return results

    async def _querymany_batch(
        self,
        query_list: List[str],
        scopes: Union[str, List[str]],
        fields: Optional[Union[str, List[str]]] = None,
        size: Optional[int] = None,
    ) -> List[Dict]:
        lines = []
        query_size = self.query_size if size is None else size
        for query_id in query_list:
            lines.append({})
            lines.append(
                {
                    "size": query_size,
                    "_source": self._source_filter(fields),
                    "query": self._scope_query(query_id, scopes),
                }
            )

        response = await self._post_ndjson("_msearch", lines)
        payload = response.json()
        responses = payload.get("responses", [])
        if len(responses) != len(query_list):
            raise RuntimeError(
                f"Elasticsearch msearch returned {len(responses)} responses for {len(query_list)} queries"
            )

        results = []
        for query_id, query_response in zip(query_list, responses):
            if "error" in query_response:
                raise RuntimeError(f"Elasticsearch query failed for {query_id}: {query_response['error']}")

            hits = query_response.get("hits", {}).get("hits", [])
            if not hits:
                results.append({"query": query_id, "notfound": True})
                continue

            for hit in hits:
                results.append(self._format_hit(hit, query=query_id))

        return results

    async def query(
        self,
        query: str,
        fields: Optional[Union[str, List[str]]] = None,
        fetch_all: bool = False,
        size: Optional[int] = None,
        skip: int = 0,
    ) -> Union[Dict, AsyncIterator[Dict]]:
        """
        Query ES using the BioThings query subset used by this project.

        Non-fetch-all queries return a BioThings-style envelope with took,
        total, max_score, and flattened hits. fetch_all=True returns an async
        iterator of flattened hits, which is used by ATC cache loading. Extra
        BioThings query kwargs such as species, facets, sort, as_dataframe, and
        return_raw are outside this adapter's supported surface.
        """
        query_clause = self._query_string_query(query)
        source_filter = self._source_filter(fields)
        query_size = self.query_size if size is None else size

        if fetch_all:
            fetch_all_size = 1000 if size is None else size
            return self._fetch_all(query_clause, source_filter, fetch_all_size)

        body = {
            "size": query_size,
            "_source": source_filter,
            "query": query_clause,
        }
        if skip:
            body["from"] = skip
        response = await self._post_json(
            "_search",
            body,
        )
        return self._format_query_response(response.json())

    async def _fetch_all(
        self,
        query_clause: Dict,
        source_filter: Union[bool, List[str]],
        page_size: int,
    ) -> AsyncIterator[Dict]:
        try:
            pit_id = await self._open_point_in_time()
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {400, 404, 405}:
                async for hit in self._fetch_all_by_offset(query_clause, source_filter, page_size):
                    yield hit
                return
            raise

        try:
            search_after = None
            while True:
                body = {
                    "size": page_size,
                    "_source": source_filter,
                    "query": query_clause,
                    "pit": {"id": pit_id, "keep_alive": "1m"},
                    "sort": [{"_shard_doc": "asc"}],
                }
                if search_after is not None:
                    body["search_after"] = search_after

                response = await self._post_root_json("_search", body)
                payload = response.json()
                pit_id = payload.get("pit_id", pit_id)
                hits = payload.get("hits", {}).get("hits", [])
                if not hits:
                    break

                for hit in hits:
                    yield self._format_hit(hit)

                search_after = hits[-1].get("sort")
                if len(hits) < page_size or search_after is None:
                    break
        finally:
            await self._close_point_in_time(pit_id)

    async def _fetch_all_by_offset(
        self,
        query_clause: Dict,
        source_filter: Union[bool, List[str]],
        page_size: int,
    ) -> AsyncIterator[Dict]:
        offset = 0
        while True:
            response = await self._post_json(
                "_search",
                {
                    "from": offset,
                    "size": page_size,
                    "_source": source_filter,
                    "query": query_clause,
                },
            )
            hits = response.json().get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                yield self._format_hit(hit)

            if len(hits) < page_size:
                break
            offset += page_size

    async def _open_point_in_time(self) -> str:
        response = await self._post("_pit", params={"keep_alive": "1m"})
        return response.json()["id"]

    async def _close_point_in_time(self, pit_id: str) -> None:
        response = await self._delete_root("_pit", json={"id": pit_id}, raise_for_status=False)
        if response.status_code == 404:
            return
        response.raise_for_status()

    async def _post_json(self, endpoint: str, body: Dict[str, Any]) -> httpx.Response:
        return await self._post(endpoint, json=body)

    async def _post_root_json(self, endpoint: str, body: Dict[str, Any]) -> httpx.Response:
        return await self._post_root(endpoint, json=body)

    async def _post_ndjson(self, endpoint: str, lines: List[Dict[str, Any]]) -> httpx.Response:
        content = "\n".join(json.dumps(line) for line in lines) + "\n"
        return await self._post(
            endpoint,
            content=content,
            headers={"Content-Type": "application/x-ndjson"},
        )

    async def _post(self, endpoint: str, **kwargs) -> httpx.Response:
        url = f"{self.host}/{self.index}/{endpoint.lstrip('/')}"
        return await self._request("POST", url, **kwargs)

    async def _post_root(self, endpoint: str, **kwargs) -> httpx.Response:
        url = f"{self.host}/{endpoint.lstrip('/')}"
        return await self._request("POST", url, **kwargs)

    async def _delete_root(self, endpoint: str, **kwargs) -> httpx.Response:
        url = f"{self.host}/{endpoint.lstrip('/')}"
        return await self._request("DELETE", url, **kwargs)

    async def _request(self, method: str, url: str, raise_for_status: bool = True, **kwargs) -> httpx.Response:
        request_headers = dict(self.headers)
        request_headers.update(kwargs.pop("headers", {}) or {})
        if request_headers:
            kwargs["headers"] = request_headers

        if self.http_client is not None:
            response = await self.http_client.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, **kwargs)

        if raise_for_status:
            response.raise_for_status()
        return response

    @staticmethod
    def _source_filter(fields: Optional[Union[str, List[str]]]) -> Union[bool, List[str]]:
        if fields is None or fields == "all":
            return True

        if isinstance(fields, str):
            return [field.strip() for field in fields.split(",") if field.strip()]

        return fields

    @staticmethod
    def _normalize_scopes(scopes: Union[str, List[str]]) -> List[str]:
        if isinstance(scopes, str):
            return [scopes]
        return scopes

    @staticmethod
    def _iter_batches(query_list: List[str], batch_size: int) -> Iterable[List[str]]:
        for index in range(0, len(query_list), batch_size):
            yield query_list[index : index + batch_size]

    def _scope_query(self, query_id: str, scopes: Union[str, List[str]]) -> Dict:
        should_queries = []
        for scope in self._normalize_scopes(scopes):
            if scope == "_id":
                should_queries.append({"ids": {"values": [query_id]}})
            else:
                should_queries.extend(
                    [
                        {"term": {scope: query_id}},
                        {"term": {f"{scope}.keyword": query_id}},
                    ]
                )

        return {
            "bool": {
                "should": should_queries,
                "minimum_should_match": 1,
            }
        }

    @staticmethod
    def _query_string_query(query: str) -> Dict:
        if query.startswith("_exists_:"):
            return {"exists": {"field": query.split(":", 1)[1]}}
        return {"query_string": {"query": query}}

    @staticmethod
    def _format_hit(hit: Dict, query: Optional[str] = None) -> Dict:
        doc = dict(hit.get("_source") or {})
        doc["_id"] = hit.get("_id")

        if hit.get("_score") is not None:
            doc["_score"] = hit["_score"]

        if query is not None:
            doc["query"] = query

        return doc

    @classmethod
    def _format_query_response(cls, response: Dict) -> Dict:
        hits_section = response.get("hits", {})
        total = hits_section.get("total", 0)
        if isinstance(total, dict):
            total = total.get("value", 0)

        return {
            "took": response.get("took"),
            "total": total,
            "max_score": hits_section.get("max_score"),
            "hits": [cls._format_hit(hit) for hit in hits_section.get("hits", [])],
        }
