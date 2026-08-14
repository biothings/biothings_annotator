"""Dedicated HTTP endpoint for PubMed document metadata."""

import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional

import sanic
from sanic.exceptions import BadRequest
from sanic.request import Request
from sanic.views import HTTPMethodView

from biothings_annotator.annotator.document_metadata import DocumentMetadataService


logger = logging.getLogger(__name__)

MAX_PUBLICATION_IDS = 100
# The index stores the PMID as the document _id and carries the DOI and PMCID in
# pubmed.identifiers. PMCID values keep PubMed's doubled form, PMC:PMC1904490
# rather than PMC:1904490. Prefix casing is accepted loosely because the index
# normalizes identifiers case-insensitively, so a mixed-case submission still
# resolves; the submitted form is what keys the response.
PUBLICATION_ID_PATTERNS = (
    re.compile(r"PMID:[1-9]\d*", re.IGNORECASE),
    re.compile(r"PMC:PMC\d+", re.IGNORECASE),
    re.compile(r"doi:10\.\d+/\S+", re.IGNORECASE),
)
SUPPORTED_PUBLICATION_ID_MESSAGE = (
    "Only PMID, PMC, and doi identifiers are supported; expected values like "
    "PMID:30690000, PMC:PMC1904490, or doi:10.1242/jcs.03153."
)


class DocumentMetadataRequestError(ValueError):
    """The publications request cannot be served as submitted."""


def _is_supported_publication_id(publication_id: object) -> bool:
    return isinstance(publication_id, str) and any(
        pattern.fullmatch(publication_id) for pattern in PUBLICATION_ID_PATTERNS
    )


def validate_publication_ids(value: object) -> List[str]:
    """Validate, deduplicate, and preserve the order of requested publication IDs."""
    if not isinstance(value, (list, tuple)) or not value:
        raise DocumentMetadataRequestError("At least one publication ID is required.")

    publication_ids = list(value)
    if len(publication_ids) > MAX_PUBLICATION_IDS:
        raise DocumentMetadataRequestError(f"A maximum of {MAX_PUBLICATION_IDS} publication IDs is allowed.")

    if not all(_is_supported_publication_id(publication_id) for publication_id in publication_ids):
        raise DocumentMetadataRequestError(SUPPORTED_PUBLICATION_ID_MESSAGE)

    return list(dict.fromkeys(publication_ids))


def parse_pubids_query(value: object) -> List[str]:
    """Parse the legacy comma-separated ``pubids`` query parameter."""
    if not isinstance(value, str) or not value:
        raise DocumentMetadataRequestError("The pubids query parameter is required.")

    publication_ids = value.split(",")
    if any(not publication_id for publication_id in publication_ids):
        raise DocumentMetadataRequestError("The pubids query parameter must be provided without empty values.")
    return validate_publication_ids(publication_ids)


class DocumentMetadataView(HTTPMethodView):
    """Serve publication metadata without entering the generic annotation path."""

    def __init__(self):
        super().__init__()
        self.document_metadata = DocumentMetadataService()

    @staticmethod
    def _request_error(error: DocumentMetadataRequestError):
        return sanic.json(
            {
                "endpoint": "/publications",
                "message": str(error),
            },
            status=400,
            headers={"Cache-Control": "no-store"},
        )

    async def _lookup(self, publication_ids: List[str], request_id: str, started_at: int):
        try:
            results, not_found = await self.document_metadata.get_publications(publication_ids)
        except Exception:
            logger.exception("Unable to retrieve PubMed document metadata")
            return sanic.json(
                {
                    "endpoint": "/publications",
                    "message": "Unable to retrieve document metadata.",
                },
                status=500,
                headers={"Cache-Control": "no-store"},
            )

        processing_time_ms = (time.perf_counter_ns() - started_at) // 1_000_000
        return sanic.json(
            {
                "_meta": {
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "n_results": len(results),
                    "request_id": request_id,
                    "processing_time_ms": processing_time_ms,
                },
                "results": results,
                "not_found": not_found,
            }
        )

    async def get(self, request: Request, publication_id: Optional[str] = None):
        started_at = time.perf_counter_ns()
        try:
            if publication_id is None:
                publication_ids = parse_pubids_query(request.args.get("pubids"))
            else:
                publication_id = urllib.parse.unquote(publication_id, encoding="utf-8", errors="strict")
                publication_ids = validate_publication_ids([publication_id])
        except DocumentMetadataRequestError as error:
            return self._request_error(error)
        except UnicodeError:
            return self._request_error(DocumentMetadataRequestError("The publication ID is not valid UTF-8."))

        return await self._lookup(
            publication_ids,
            request.args.get("request_id", ""),
            started_at,
        )

    async def post(self, request: Request):
        started_at = time.perf_counter_ns()
        try:
            body = request.json
        except BadRequest:
            return self._request_error(DocumentMetadataRequestError("The request body must contain valid JSON."))

        publication_ids = body.get("ids") if isinstance(body, dict) else body
        try:
            publication_ids = validate_publication_ids(publication_ids)
        except DocumentMetadataRequestError as error:
            return self._request_error(error)

        request_id = request.args.get("request_id", "")
        if isinstance(body, dict):
            request_id = body.get("request_id", request_id)
        if not isinstance(request_id, str):
            return self._request_error(DocumentMetadataRequestError("request_id must be a string."))

        return await self._lookup(publication_ids, request_id, started_at)
