"""Fast PubMed-only document metadata lookups."""

import asyncio
import os
from typing import Dict, Iterable, List, Optional, Tuple

from biothings_annotator.annotator.settings import (
    DOCUMENT_METADATA_REQUEST_TIMEOUT,
    DOCUMENT_METADATA_TWO_PHASE_LOOKUP,
    ELASTICSEARCH_CONNECTION,
)
from biothings_annotator.annotator.utils import get_elasticsearch_client

PUBMED_SOURCE_FIELDS = ["pubmed"]
PUBMED_IDENTIFIER_SCOPES = ["pubmed.identifiers"]
PMID_PREFIX = "PMID"
# Multi-identifier lookup cannot work at all without the identifiers field, so
# its absence is a capability gap. pubdate_raw only changes how precisely a date
# is projected and has a working fallback, so its absence is informational.
PUBMED_REQUIRED_INDEX_FIELDS = ("pubmed.identifiers",)
# Confirmed against the ingest side: whatever the upstream exporter emits, the
# in-house transformation lands the verbatim value in pubmed.pubdate_raw, so that
# is the field the capability probe checks.
PUBMED_OPTIONAL_INDEX_FIELDS = ("pubmed.pubdate_raw",)
# Used only by the numeric pub_date fallback. The verbatim pubdate_raw path
# already carries PubMed's own three-letter abbreviations.
MONTH_ABBREVIATIONS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _is_document_id(publication_id: str) -> bool:
    """A PMID is the index's document ``_id``; every other prefix needs a search."""
    return publication_id.split(":", 1)[0].upper() == PMID_PREFIX


def _canonical_lookup_id(publication_id: str) -> str:
    """Normalize a PMID prefix to the casing the index stores it under.

    Elasticsearch matches ``_id`` byte-exactly, so a submitted ``pmid:30690000``
    misses the document stored as ``PMID:30690000`` and would be reported absent.
    The endpoint accepts the prefix case-insensitively, so the casing has to be
    repaired here rather than rejected there. Only the prefix is touched; the
    digits carry no case. DOI and PMCID resolve through the case-insensitive
    ``identifiers`` field instead of ``_id``, so they pass through unchanged.
    """
    prefix, separator, suffix = publication_id.partition(":")
    if separator and prefix.upper() == PMID_PREFIX:
        return f"{PMID_PREFIX}{separator}{suffix}"
    return publication_id


def _is_bare_year_range(value: str) -> bool:
    """Detect a spaceless verbatim year range such as ``"1987-1988"``.

    This shape collides with an ISO date: both open with ``YYYY-``. Only a
    four-digit tail is treated as a range, because ``"2026-07"`` is a valid ISO
    year-month and a two-digit tail cannot be told apart from a month. A range
    written that way therefore keeps its existing ISO reading rather than
    guessing.
    """
    head, separator, tail = value.partition("-")
    return bool(separator) and len(head) == 4 and head.isdigit() and len(tail) == 4 and tail.isdigit()


def _raw_publication_date_components(pubdate_raw: object) -> Tuple[str, str, str]:
    """Split PubMed's verbatim publication date into the legacy response fields.

    ``pubdate_raw`` preserves PubMed's own rendering, which includes season and
    month ranges (``"1994 Sep-Dec"``) and spans crossing a year boundary
    (``"1998 Dec-1999 Jan"``). A range is expected output rather than an error,
    so everything after the leading year is carried through verbatim and only a
    trailing bare day number is split off. No month conversion happens here:
    the raw value already carries capitalized three-letter abbreviations.
    """
    if not isinstance(pubdate_raw, str):
        return "", "", ""

    parts = pubdate_raw.strip().split(maxsplit=1)
    if not parts:
        return "", "", ""

    # A bare year range has no whitespace, so the leading token is the whole
    # expression. The legacy fields have no home for a second year and pub_month
    # would misfile one, so pub_year carries the range verbatim rather than
    # truncating to its opening year.
    if len(parts) == 1 and _is_bare_year_range(parts[0]):
        return parts[0], "", ""

    if len(parts[0]) != 4 or not parts[0].isdigit():
        return "", "", ""

    year = parts[0]
    remainder = parts[1].strip() if len(parts) > 1 else ""
    if not remainder:
        return year, "", ""

    head, _, tail = remainder.rpartition(" ")
    if head and tail.isdigit() and 1 <= int(tail) <= 31:
        return year, head.strip(), str(int(tail))
    return year, remainder, ""


def _iso_publication_date_components(publication_date: object) -> Tuple[str, str, str]:
    """Convert the indexed ISO date precision into legacy response fields."""
    if not isinstance(publication_date, str):
        return "", "", ""

    parts = publication_date.strip().split("-")
    if not parts or len(parts[0]) != 4 or not parts[0].isdigit():
        return "", "", ""

    year = parts[0]
    month = ""
    day = ""
    if len(parts) >= 2 and parts[1].isdigit():
        month_number = int(parts[1])
        if 1 <= month_number <= 12:
            month = MONTH_ABBREVIATIONS[month_number]
    if len(parts) >= 3 and parts[2].isdigit():
        day_number = int(parts[2])
        if 1 <= day_number <= 31:
            day = str(day_number)
    return year, month, day


def _publication_date_components(metadata: Dict) -> Tuple[str, str, str]:
    """Prefer PubMed's verbatim date, falling back to the indexed ISO date.

    ``pubdate_raw`` is the richer source because it retains ranges that an exact
    calendar date cannot express, but it depends on an index revision that may
    not be deployed yet, and it is absent or unparseable for records with no
    stated date. The ISO fallback keeps those records projecting as they do
    today.

    The index carries the verbatim value in ``pubdate_raw``, so the matching read
    of ``pub_date`` below is defensive: it costs one call and stops a verbatim
    value landing there from being flattened to empty strings if the ingest
    transformation ever changes. It cannot misread anything, because the two
    parsers accept disjoint shapes — an ISO date is only ever claimed by the ISO
    parser and a range only by the verbatim one.
    """
    year, month, day = _raw_publication_date_components(metadata.get("pubdate_raw"))
    if year:
        return year, month, day

    publication_date = metadata.get("pub_date")
    # The verbatim reading is tried first because a bare year range and an ISO
    # date share their leading shape: the ISO parser would claim "1987-1988",
    # return just "1987", and silently drop the closing year. The verbatim parser
    # declines anything ISO-shaped, so nothing else changes hands.
    year, month, day = _raw_publication_date_components(publication_date)
    if year:
        return year, month, day
    return _iso_publication_date_components(publication_date)


def format_publication_metadata(metadata: Dict) -> Dict[str, str]:
    """Translate the compact indexed PubMed object into the legacy field names."""
    journal = metadata.get("journal")
    if not isinstance(journal, dict):
        journal = {}
    publication_year, publication_month, publication_day = _publication_date_components(metadata)

    fields = {
        "journal_name": journal.get("name"),
        "journal_abbrev": journal.get("abbr"),
        "article_title": metadata.get("title"),
        "volume": metadata.get("vol"),
        "issue": metadata.get("iss"),
        "pub_year": publication_year,
        "pub_month": publication_month,
        "pub_day": publication_day,
        "abstract": metadata.get("abstract"),
    }
    return {field: value if isinstance(value, str) else "" for field, value in fields.items()}


def _is_searchable(field_capabilities: object) -> bool:
    """Report whether ``_field_caps`` says a present field can actually be queried.

    A field mapped with ``index: false`` still appears in the field-caps response,
    but every type entry under it is flagged unsearchable. For a scoped DOI or
    PMCID lookup that is indistinguishable from the field being absent: the term
    query matches nothing and raises no error. A field can be mapped under more
    than one type, so one searchable type is enough.
    """
    if not isinstance(field_capabilities, dict):
        return False
    return any(
        isinstance(type_capabilities, dict) and type_capabilities.get("searchable") is True
        for type_capabilities in field_capabilities.values()
    )


class DocumentMetadataService:
    """Retrieve only PubMed metadata from the dedicated Elasticsearch alias."""

    def __init__(
        self,
        elasticsearch_connection: Optional[str] = None,
        request_timeout: Optional[float] = None,
        two_phase_lookup: Optional[bool] = None,
    ):
        self.elasticsearch_connection = (
            elasticsearch_connection or os.environ.get("ELASTICSEARCH_CONNECTION", ELASTICSEARCH_CONNECTION)
        ).strip()
        configured_timeout = request_timeout
        if configured_timeout is None:
            configured_timeout = os.environ.get(
                "DOCUMENT_METADATA_REQUEST_TIMEOUT",
                DOCUMENT_METADATA_REQUEST_TIMEOUT,
            )
        self.request_timeout = float(configured_timeout)
        if self.request_timeout <= 0:
            raise ValueError("Document metadata request timeout must be greater than zero")

        configured_two_phase = two_phase_lookup
        if configured_two_phase is None:
            configured_two_phase = os.environ.get("DOCUMENT_METADATA_TWO_PHASE_LOOKUP")
            if configured_two_phase is None:
                configured_two_phase = DOCUMENT_METADATA_TWO_PHASE_LOOKUP
            else:
                configured_two_phase = configured_two_phase.strip().lower() in ("1", "true", "yes", "on")
        self.two_phase_lookup = bool(configured_two_phase)

    async def get_publications(self, publication_ids: Iterable[str]) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
        """Return ordered publication results and missing identifiers."""
        publication_ids = list(publication_ids)
        if not publication_ids:
            return {}, []

        # Two spellings of one PMID collapse to a single lookup but stay separate
        # response keys, so the backend is never asked for the same _id twice.
        document_ids: List[str] = []
        search_ids: List[str] = []
        for publication_id in publication_ids:
            if _is_document_id(publication_id):
                canonical_id = _canonical_lookup_id(publication_id)
                if canonical_id not in document_ids:
                    document_ids.append(canonical_id)
            else:
                search_ids.append(publication_id)

        client = get_elasticsearch_client("pubmed", self.elasticsearch_connection)
        fetch = self._fetch_hits_two_phase if self.two_phase_lookup else self._fetch_hits
        hits_by_id = await asyncio.wait_for(
            fetch(client, document_ids, search_ids),
            timeout=self.request_timeout,
        )

        results: Dict[str, Dict[str, str]] = {}
        not_found: List[str] = []
        for publication_id in publication_ids:
            metadata = hits_by_id.get(_canonical_lookup_id(publication_id), {}).get("pubmed")
            if not isinstance(metadata, dict):
                not_found.append(publication_id)
                continue
            results[publication_id] = format_publication_metadata(metadata)
        return results, not_found

    @staticmethod
    async def _fetch_hits(client, document_ids: List[str], search_ids: List[str]) -> Dict[str, Dict]:
        """Resolve hits by submitted identifier, keeping PMIDs on the exact-ID path.

        PMIDs are the document ``_id``, so they keep the single-request ``mget``
        fast path that the service's latency budget is built around. Only DOI and
        PMCID pay for the scoped lookup, which costs one ``_msearch`` entry per
        identifier. Both calls echo the submitted identifier back as ``query``,
        which is what maps a DOI hit to its request key rather than to the PMID
        the document is stored under.
        """
        lookups = []
        if document_ids:
            lookups.append(client.mget(document_ids, fields=PUBMED_SOURCE_FIELDS))
        if search_ids:
            lookups.append(
                client.querymany(
                    search_ids,
                    scopes=PUBMED_IDENTIFIER_SCOPES,
                    fields=PUBMED_SOURCE_FIELDS,
                    size=1,
                )
            )

        hits_by_id: Dict[str, Dict] = {}
        for hits in await asyncio.gather(*lookups):
            for hit in hits:
                if hit.get("notfound"):
                    continue
                hits_by_id.setdefault(hit.get("query"), hit)
        return hits_by_id

    @staticmethod
    async def _fetch_hits_two_phase(client, document_ids: List[str], search_ids: List[str]) -> Dict[str, Dict]:
        """Resolve identifiers to document ``_id``s first, then fetch source once.

        The one-phase path above fetches full source on both legs concurrently.
        This one asks the ``_msearch`` only for ``_id`` -- so Elasticsearch never
        loads a matched abstract on the search leg -- and then retrieves every
        document, resolved and submitted alike, through a single ``_mget`` on the
        exact-ID path.

        The trade is real in both directions and is why this is a flag rather
        than a replacement. It removes source loading from the search leg and
        collapses two source fetches into one batched request, but it serializes
        what the one-phase path runs concurrently: the ``_mget`` cannot start
        until the ``_msearch`` returns. A PMID-heavy batch currently hides the
        whole DOI lookup behind the PMID fetch and would lose that overlap, while
        a DOI-heavy batch has little overlap to lose. Measure per workload.

        Note that this does not address the ``_msearch``'s dominant cost. A term
        query on ``pubmed.identifiers`` carries no routing key, so every entry
        executes on every shard regardless of how little it returns; only the
        fetch phase gets cheaper here. Removing the fan-out would mean making
        DOI and PMCID resolvable by ``_id`` instead of by query.
        """
        # Several submitted identifiers can name one document -- a DOI and the
        # PMID of the same paper, or a DOI and its PMCID -- so resolution is kept
        # as a mapping and the fetch list is deduplicated. The response has to be
        # keyed by what the caller submitted, which is what this mapping
        # preserves and what a bare _id lookup would lose.
        resolved_by_submitted: Dict[str, str] = {}
        if search_ids:
            identifier_hits = await client.querymany_ids(
                search_ids,
                scopes=PUBMED_IDENTIFIER_SCOPES,
                size=1,
            )
            for hit in identifier_hits:
                if hit.get("notfound"):
                    continue
                document_id = hit.get("_id")
                if document_id:
                    resolved_by_submitted[hit.get("query")] = document_id

        fetch_ids = list(dict.fromkeys([*document_ids, *resolved_by_submitted.values()]))
        if not fetch_ids:
            return {}

        hits_by_document_id: Dict[str, Dict] = {}
        for hit in await client.mget(fetch_ids, fields=PUBMED_SOURCE_FIELDS):
            if hit.get("notfound"):
                continue
            hits_by_document_id.setdefault(hit.get("query"), hit)

        # Re-key onto submitted identifiers. A PMID is already its own document
        # _id; a DOI or PMCID has to travel back through the resolution mapping.
        hits_by_id: Dict[str, Dict] = {}
        for document_id in document_ids:
            hit = hits_by_document_id.get(document_id)
            if hit is not None:
                hits_by_id[document_id] = hit
        for submitted, document_id in resolved_by_submitted.items():
            hit = hits_by_document_id.get(document_id)
            if hit is not None:
                hits_by_id[submitted] = hit
        return hits_by_id

    async def check_index_fields(self) -> Dict[str, object]:
        """Report whether the live index mapping can support multi-identifier lookup.

        A DOI or PMCID lookup against an index without ``pubmed.identifiers``
        returns zero hits and no error, so on its own it is indistinguishable from
        a genuinely absent paper. Probing the mapping separates the two. It stays
        useful after the reindex ships, because it also catches a later reindex
        that drops the field or an alias repointed at a stale index.

        This reports rather than raises: the field is legitimately absent until
        the reindex happens, so a fatal check here would refuse to serve the PMID
        fast path that does work.
        """
        client = get_elasticsearch_client("pubmed", self.elasticsearch_connection)
        probed_fields = PUBMED_REQUIRED_INDEX_FIELDS + PUBMED_OPTIONAL_INDEX_FIELDS
        capabilities = await asyncio.wait_for(
            client.field_capabilities(list(probed_fields)),
            timeout=self.request_timeout,
        )

        # "fields" reports mapping presence; the required-field gate additionally
        # demands searchability. A field that is present but unsearchable therefore
        # shows as fields[f] = true while still appearing in missing_required_fields,
        # which is precisely the "mapped with index: false" diagnosis.
        present = {field: field in capabilities for field in probed_fields}
        missing_required = sorted(
            field for field in PUBMED_REQUIRED_INDEX_FIELDS if not _is_searchable(capabilities.get(field))
        )
        return {
            "index": client.index,
            "fields": present,
            "missing_required_fields": missing_required,
            "multi_identifier_lookup": not missing_required,
            "verbatim_publication_date": all(present[field] for field in PUBMED_OPTIONAL_INDEX_FIELDS),
        }
