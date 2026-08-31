"""Fast PubMed-only document metadata lookups."""

import asyncio
import os
from typing import Dict, Iterable, List, Optional, Tuple

from biothings_annotator.annotator.settings import (
    DOCUMENT_METADATA_REQUEST_TIMEOUT,
    ELASTICSEARCH_CONNECTION,
)
from biothings_annotator.annotator.utils import get_elasticsearch_client

PUBMED_SOURCE_FIELDS = ["pubmed"]
PUBMED_IDENTIFIER_FIELD = "pubmed.identifiers"
PMID_PREFIX = "PMID"
CURRENT_LOOKUP_STRATEGY = "current"
BULK_SEARCH_LOOKUP_STRATEGY = "bulk-search"
COMBINED_SEARCH_LOOKUP_STRATEGY = "combined-search"
DOCUMENT_METADATA_LOOKUP_STRATEGIES = (
    CURRENT_LOOKUP_STRATEGY,
    BULK_SEARCH_LOOKUP_STRATEGY,
    COMBINED_SEARCH_LOOKUP_STRATEGY,
)
COMBINED_SEARCH_MAX_HITS = 100
DOCUMENT_IDS_MATCH = "document_ids"
ALTERNATIVE_IDENTIFIERS_MATCH = "alternative_identifiers"
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


async def _empty_hits() -> List[Dict]:
    """Supply an awaitable empty lookup so both strategy legs share one gather."""
    return []


async def _empty_lookup_execution() -> Tuple[List[Dict], bool]:
    """Supply an empty hit list and a no-fallback execution marker."""
    return [], False


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
        lookup_strategy: str = CURRENT_LOOKUP_STRATEGY,
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
        if lookup_strategy not in DOCUMENT_METADATA_LOOKUP_STRATEGIES:
            raise ValueError(f"lookup_strategy must be one of {DOCUMENT_METADATA_LOOKUP_STRATEGIES}")
        self.lookup_strategy = lookup_strategy

    async def get_publications(self, publication_ids: Iterable[str]) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
        """Return ordered publication results and missing identifiers.

        The historical two-tuple stays stable for non-HTTP callers. The view
        uses :meth:`get_publications_with_metadata` to expose per-request lookup
        execution metadata without storing mutable state on this shared service.
        """
        results, not_found, _ = await self.get_publications_with_metadata(publication_ids)
        return results, not_found

    async def get_publications_with_metadata(
        self,
        publication_ids: Iterable[str],
    ) -> Tuple[Dict[str, Dict[str, str]], List[str], bool]:
        """Return publication results plus whether a speculative lookup fell back."""
        publication_ids = list(publication_ids)
        if not publication_ids:
            return {}, [], False

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
        if self.lookup_strategy == COMBINED_SEARCH_LOOKUP_STRATEGY:
            fetch = self._fetch_hits_combined_search_execution
        elif self.lookup_strategy == BULK_SEARCH_LOOKUP_STRATEGY:
            fetch = self._fetch_hits_bulk_search_execution
        else:
            fetch = self._fetch_hits_execution

        hits_by_id, lookup_fallback = await asyncio.wait_for(
            fetch(client, document_ids, search_ids), timeout=self.request_timeout
        )

        results: Dict[str, Dict[str, str]] = {}
        not_found: List[str] = []
        for publication_id in publication_ids:
            metadata = hits_by_id.get(_canonical_lookup_id(publication_id), {}).get("pubmed")
            if not isinstance(metadata, dict):
                not_found.append(publication_id)
                continue
            results[publication_id] = format_publication_metadata(metadata)
        return results, not_found, lookup_fallback

    @staticmethod
    async def _fetch_hits(client, document_ids: List[str], search_ids: List[str]) -> Dict[str, Dict]:
        """Resolve hits by submitted identifier, keeping PMIDs on the exact-ID path.

        PMIDs are the document ``_id``, so they keep the single-request ``mget``
        fast path that the service's latency budget is built around. Only DOI and
        PMCID pay for the scoped lookup, which costs one ``_msearch`` entry per
        identifier. Both calls echo the submitted identifier back as ``query``,
        which is what maps a DOI hit to its request key rather than to the PMID
        the document is stored under.

        The PubMed mapping is known: ``pubmed.identifiers`` is itself a
        case-normalized ``keyword`` field.  The exact helper therefore queries
        only that root field instead of also sending the generic adapter's
        ``.keyword`` compatibility clause, which cannot exist beneath a keyword
        field.
        """
        lookups = []
        if document_ids:
            lookups.append(client.mget(document_ids, fields=PUBMED_SOURCE_FIELDS))
        if search_ids:
            lookups.append(
                client.querymany_exact(
                    search_ids,
                    field=PUBMED_IDENTIFIER_FIELD,
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
    async def _fetch_hits_execution(
        client,
        document_ids: List[str],
        search_ids: List[str],
    ) -> Tuple[Dict[str, Dict], bool]:
        return await DocumentMetadataService._fetch_hits(client, document_ids, search_ids), False

    @staticmethod
    async def _fetch_hits_bulk_search(client, document_ids: List[str], search_ids: List[str]) -> Dict[str, Dict]:
        hits_by_id, _ = await DocumentMetadataService._fetch_hits_bulk_search_execution(
            client,
            document_ids,
            search_ids,
        )
        return hits_by_id

    @staticmethod
    async def _fetch_hits_bulk_search_execution(
        client,
        document_ids: List[str],
        search_ids: List[str],
    ) -> Tuple[Dict[str, Dict], bool]:
        """Run ``_mget`` and one alternative-identifier ``terms`` search together.

        Elasticsearch returns documents, not the submitted terms that matched
        them, so the search hits are re-keyed from ``pubmed.identifiers``.  The
        whole alternative batch falls back to the exact per-ID ``_msearch`` if
        that reverse mapping is incomplete or ambiguous.  The PMID ``_mget`` is
        never repeated, and its results are deliberately not used to prune the
        search: both normal-path backend requests start concurrently.
        """
        document_lookup = client.mget(document_ids, fields=PUBMED_SOURCE_FIELDS) if document_ids else _empty_hits()
        search_lookup = (
            DocumentMetadataService._fetch_bulk_search_hits_execution(client, search_ids)
            if search_ids
            else _empty_lookup_execution()
        )
        document_hits, (search_hits, lookup_fallback) = await asyncio.gather(document_lookup, search_lookup)

        hits_by_id: Dict[str, Dict] = {}
        for hit in [*document_hits, *search_hits]:
            if hit.get("notfound"):
                continue
            hits_by_id.setdefault(hit.get("query"), hit)
        return hits_by_id, lookup_fallback

    @staticmethod
    async def _fetch_bulk_search_hits(client, search_ids: List[str]) -> List[Dict]:
        hits, _ = await DocumentMetadataService._fetch_bulk_search_hits_execution(client, search_ids)
        return hits

    @staticmethod
    async def _fetch_bulk_search_hits_execution(client, search_ids: List[str]) -> Tuple[List[Dict], bool]:
        """Return bulk hits keyed onto every submitted alternative identifier."""
        # The deployed keyword normalizer lowercases identifiers. Python and
        # Lucene agree for the ASCII identifiers used by PubMed; unusual Unicode
        # DOI suffixes take the proven exact-msearch path instead of relying on
        # subtly different Unicode case tables.
        if any(not identifier.isascii() for identifier in search_ids):
            return await DocumentMetadataService._fetch_exact_search_hits(client, search_ids), False

        submitted_by_normalized: Dict[str, List[str]] = {}
        for submitted in search_ids:
            submitted_by_normalized.setdefault(submitted.lower(), []).append(submitted)
        normalized_ids = list(submitted_by_normalized)

        response = await client.search_terms(
            normalized_ids,
            field=PUBMED_IDENTIFIER_FIELD,
            fields=PUBMED_SOURCE_FIELDS,
            size=len(normalized_ids),
        )
        hits = response.get("hits")
        if (
            response.get("timed_out", False) is not False
            or response.get("failed_shards", 0) != 0
            or response.get("total_relation") != "eq"
            or not isinstance(response.get("total"), int)
            or not isinstance(hits, list)
            or response.get("total") != len(hits)
        ):
            return await DocumentMetadataService._fetch_exact_search_hits(client, search_ids), True

        owners: Dict[str, str] = {}
        rekeyed: List[Dict] = []
        for hit in hits:
            if not isinstance(hit, dict) or not isinstance(hit.get("_id"), str):
                return await DocumentMetadataService._fetch_exact_search_hits(client, search_ids), True
            pubmed = hit.get("pubmed")
            identifiers = pubmed.get("identifiers") if isinstance(pubmed, dict) else None
            if not isinstance(identifiers, list) or not all(isinstance(value, str) for value in identifiers):
                return await DocumentMetadataService._fetch_exact_search_hits(client, search_ids), True

            matched = {
                value.lower() for value in identifiers if value.isascii() and value.lower() in submitted_by_normalized
            }
            if not matched:
                return await DocumentMetadataService._fetch_exact_search_hits(client, search_ids), True

            for normalized in matched:
                previous_owner = owners.setdefault(normalized, hit["_id"])
                if previous_owner != hit["_id"]:
                    return await DocumentMetadataService._fetch_exact_search_hits(client, search_ids), True
                for submitted in submitted_by_normalized[normalized]:
                    rekeyed.append({**hit, "query": submitted})
        return rekeyed, False

    @staticmethod
    async def _fetch_exact_search_hits(client, search_ids: List[str]) -> List[Dict]:
        return await client.querymany_exact(
            search_ids,
            field=PUBMED_IDENTIFIER_FIELD,
            fields=PUBMED_SOURCE_FIELDS,
            size=1,
        )

    @staticmethod
    async def _fetch_hits_combined_search(
        client,
        document_ids: List[str],
        search_ids: List[str],
    ) -> Dict[str, Dict]:
        hits_by_id, _ = await DocumentMetadataService._fetch_hits_combined_search_execution(
            client,
            document_ids,
            search_ids,
        )
        return hits_by_id

    @staticmethod
    async def _fetch_hits_combined_search_execution(
        client,
        document_ids: List[str],
        search_ids: List[str],
    ) -> Tuple[Dict[str, Dict], bool]:
        """Resolve PMIDs, DOI, and PMCID values with one ordinary search.

        The normal path sends one OR query containing an ``ids`` clause for
        canonical PMIDs and one exact ``terms`` clause for normalized alternate
        identifiers. Elasticsearch returns documents rather than submitted
        values, so every hit is reverse-mapped to all request spellings it owns.
        Any result shape that cannot prove that mapping complete and unambiguous
        falls back for the whole request to the current mget + exact-msearch path.
        """
        # With no PMID clause this is byte-for-byte the existing bulk strategy.
        # Keeping that arm identical provides a true 0/100 control in the A/B
        # matrix instead of measuring a gratuitous bool/named-query wrapper.
        if not document_ids:
            return await DocumentMetadataService._fetch_hits_bulk_search_execution(client, [], search_ids)

        if any(not identifier.isascii() for identifier in search_ids):
            return await DocumentMetadataService._fetch_hits(client, document_ids, search_ids), False

        submitted_by_normalized: Dict[str, List[str]] = {}
        for submitted in search_ids:
            submitted_by_normalized.setdefault(submitted.lower(), []).append(submitted)
        normalized_ids = list(submitted_by_normalized)
        requested_hit_capacity = len(document_ids) + len(normalized_ids)

        response = await client.search_ids_or_terms(
            document_ids,
            normalized_ids,
            field=PUBMED_IDENTIFIER_FIELD,
            fields=PUBMED_SOURCE_FIELDS,
            size=min(requested_hit_capacity, COMBINED_SEARCH_MAX_HITS),
        )
        hits_by_id = DocumentMetadataService._reverse_combined_search_hits(
            response,
            document_ids,
            submitted_by_normalized,
        )
        if hits_by_id is None:
            return await DocumentMetadataService._fetch_hits(client, document_ids, search_ids), True
        return hits_by_id, False

    @staticmethod
    def _reverse_combined_search_hits(
        response: object,
        document_ids: List[str],
        submitted_by_normalized: Dict[str, List[str]],
    ) -> Optional[Dict[str, Dict]]:
        """Return a proven identifier-to-hit mapping, or ``None`` if unsafe."""
        if not isinstance(response, dict):
            return None
        hits = response.get("hits")
        total = response.get("total")
        failed_shards = response.get("failed_shards")
        if (
            response.get("timed_out") is not False
            or response.get("terminated_early", False) is not False
            or not isinstance(failed_shards, int)
            or isinstance(failed_shards, bool)
            or failed_shards != 0
            or response.get("total_relation") != "eq"
            or not isinstance(total, int)
            or isinstance(total, bool)
            or total < 0
            or not isinstance(hits, list)
            or total != len(hits)
        ):
            return None

        requested_document_ids = set(document_ids)
        alternate_owners: Dict[str, str] = {}
        seen_hit_ids = set()
        hits_by_id: Dict[str, Dict] = {}
        for hit in hits:
            if not isinstance(hit, dict):
                return None
            hit_id = hit.get("_id")
            pubmed = hit.get("pubmed")
            matched_queries = hit.get("_matched_queries")
            if (
                not isinstance(hit_id, str)
                or hit_id in seen_hit_ids
                or not isinstance(pubmed, dict)
                or not isinstance(matched_queries, list)
                or not all(isinstance(query_name, str) for query_name in matched_queries)
            ):
                return None
            seen_hit_ids.add(hit_id)

            matched_query_names = set(matched_queries)
            if not matched_query_names or not matched_query_names.issubset(
                {DOCUMENT_IDS_MATCH, ALTERNATIVE_IDENTIFIERS_MATCH}
            ):
                return None

            assigned = False
            if DOCUMENT_IDS_MATCH in matched_query_names:
                if hit_id not in requested_document_ids:
                    return None
                hits_by_id[hit_id] = hit
                assigned = True
            elif hit_id in requested_document_ids:
                # Named-query attribution must agree with the exact hit ID. A
                # mismatch here means the response cannot be audited safely.
                return None

            if ALTERNATIVE_IDENTIFIERS_MATCH in matched_query_names:
                identifiers = pubmed.get("identifiers")
                if not isinstance(identifiers, list) or not all(isinstance(value, str) for value in identifiers):
                    return None
                matched_identifiers = {
                    value.lower()
                    for value in identifiers
                    if value.isascii() and value.lower() in submitted_by_normalized
                }
                if not matched_identifiers:
                    return None

                for normalized in matched_identifiers:
                    previous_owner = alternate_owners.setdefault(normalized, hit_id)
                    if previous_owner != hit_id:
                        return None
                    for submitted in submitted_by_normalized[normalized]:
                        hits_by_id[submitted] = hit
                assigned = True

            if not assigned:
                return None
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
