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
# Temporary single-deployment A/B hook for the CCWG#15 benchmark. Keep it out of
# OpenAPI and remove it with the losing lookup implementation after measurement.
PUBLICATIONS_LOOKUP_STRATEGY_HEADER = "X-Publications-Lookup-Strategy"
CURRENT_LOOKUP_STRATEGY = "current"
TWO_PHASE_LOOKUP_STRATEGY = "two-phase"
PUBLICATIONS_LOOKUP_STRATEGIES = (CURRENT_LOOKUP_STRATEGY, TWO_PHASE_LOOKUP_STRATEGY)
# The index stores the PMID as the document _id and carries the DOI and PMCID in
# pubmed.identifiers. PMCID values keep PubMed's doubled form, PMC:PMC1904490
# rather than PMC:1904490. Prefix casing is accepted loosely: DOI and PMCID
# resolve through the case-insensitive identifiers field, and a PMID prefix is
# canonicalized before the exact-_id lookup. Either way the submitted form is
# what keys the response.
# These mirror the OpenAPI PublicationId alternation character-for-character so
# served validation and the published contract cannot drift. That is why the
# prefixes are spelled out as explicit case pairs instead of using re.IGNORECASE,
# and why the digits are [0-9] rather than \d:
#   - re.IGNORECASE applies Unicode case folding, which accepts prefixes like
#     "doİ:" and "PMİD:" that the documented classes reject.
#   - \d accepts Unicode decimal digits, which accepts "PMID:1\u0662".
# Neither can ever match the ASCII identifiers stored in the index. Adding
# re.ASCII would fix both but would also narrow \S in the DOI suffix, which the
# documented pattern leaves Unicode-wide, so it would trade one drift for another.
PUBLICATION_ID_PATTERNS = (
    re.compile(r"[Pp][Mm][Ii][Dd]:[1-9][0-9]*"),
    re.compile(r"[Pp][Mm][Cc]:[Pp][Mm][Cc][0-9]+"),
    re.compile(r"[Dd][Oo][Ii]:10\.[0-9]+/\S+"),
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

    # HTTPMethodView constructs a view object for every request, so these live on
    # the class to provide exactly two fixed service instances per worker.
    # Mutating one shared service's ``two_phase_lookup`` flag would race when
    # current and two-phase requests overlap in the same worker.
    document_metadata = DocumentMetadataService(two_phase_lookup=False)
    two_phase_document_metadata = DocumentMetadataService(two_phase_lookup=True)

    @staticmethod
    def _lookup_strategy(request: Request) -> str:
        lookup_strategy = request.headers.get(
            PUBLICATIONS_LOOKUP_STRATEGY_HEADER,
            CURRENT_LOOKUP_STRATEGY,
        )
        if lookup_strategy not in PUBLICATIONS_LOOKUP_STRATEGIES:
            raise DocumentMetadataRequestError(
                f"The {PUBLICATIONS_LOOKUP_STRATEGY_HEADER} header must be either "
                f"{CURRENT_LOOKUP_STRATEGY} or {TWO_PHASE_LOOKUP_STRATEGY}."
            )
        return lookup_strategy

    def _service_for_lookup_strategy(self, lookup_strategy: str) -> DocumentMetadataService:
        if lookup_strategy == TWO_PHASE_LOOKUP_STRATEGY:
            return self.two_phase_document_metadata
        return self.document_metadata

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

    async def _lookup(
        self,
        publication_ids: List[str],
        request_id: str,
        lookup_strategy: str,
        started_at: int,
    ):
        document_metadata = self._service_for_lookup_strategy(lookup_strategy)
        try:
            results, not_found = await document_metadata.get_publications(publication_ids)
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
                    "lookup_strategy": lookup_strategy,
                },
                "results": results,
                "not_found": not_found,
            },
            # The temporary strategy selector changes _meta and may change
            # timing/content if an implementation is incorrect.  A shared HTTP
            # cache must never reuse one arm's response for the other arm.
            headers={"Vary": PUBLICATIONS_LOOKUP_STRATEGY_HEADER},
        )

    async def get(self, request: Request, publication_id: Optional[str] = None):
        started_at = time.perf_counter_ns()
        try:
            lookup_strategy = self._lookup_strategy(request)
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
            lookup_strategy,
            started_at,
        )

    async def post(self, request: Request):
        started_at = time.perf_counter_ns()
        try:
            lookup_strategy = self._lookup_strategy(request)
        except DocumentMetadataRequestError as error:
            return self._request_error(error)

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

        return await self._lookup(publication_ids, request_id, lookup_strategy, started_at)
