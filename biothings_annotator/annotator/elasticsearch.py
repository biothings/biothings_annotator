"""
Elasticsearch-backed query adapter for annotator data.
"""

import json
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Union

import httpx


class ElasticsearchAnnotatorClient:
    """
    Small async REST adapter that mirrors the BioThings methods used by the annotator.
    """

    def __init__(
        self,
        host: str,
        index: str,
        query_size: int = 10,
        timeout: Union[int, float] = 30,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.host = host.rstrip("/")
        self.index = index
        self.query_size = query_size
        self.timeout = timeout
        self.http_client = http_client

    #todo match biothings client `querymany` pagination - could be direct import from SDK
    async def querymany(
        self,
        query_list: Iterable[str],
        scopes: Union[str, List[str]],
        fields: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict]:
        """
        Query ES once per input ID and return BioThings-style hits with a query field.
        """
        query_list = list(query_list)
        if not query_list:
            return []

        lines = []
        for query_id in query_list:
            lines.append({})
            lines.append(
                {
                    "size": self.query_size,
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
    ) -> Union[List[Dict], AsyncIterator[Dict]]:
        """
        Query ES using a BioThings-like query string.
        """
        query_clause = self._query_string_query(query)
        source_filter = self._source_filter(fields)

        if fetch_all:
            return self._fetch_all(query_clause, source_filter)

        response = await self._post_json(
            "_search",
            {
                "size": self.query_size,
                "_source": source_filter,
                "query": query_clause,
            },
        )
        hits = response.json().get("hits", {}).get("hits", [])
        return [self._format_hit(hit) for hit in hits]

    async def _fetch_all(self, query_clause: Dict, source_filter: Union[bool, List[str]]) -> AsyncIterator[Dict]:
        offset = 0
        page_size = 1000
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

    async def _post_json(self, endpoint: str, body: Dict[str, Any]) -> httpx.Response:
        return await self._post(endpoint, json=body)

    async def _post_ndjson(self, endpoint: str, lines: List[Dict[str, Any]]) -> httpx.Response:
        content = "\n".join(json.dumps(line) for line in lines) + "\n"
        return await self._post(
            endpoint,
            content=content,
            headers={"Content-Type": "application/x-ndjson"},
        )

    async def _post(self, endpoint: str, **kwargs) -> httpx.Response:
        url = f"{self.host}/{self.index}/{endpoint.lstrip('/')}"
        if self.http_client is not None:
            response = await self.http_client.post(url, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, **kwargs)

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
