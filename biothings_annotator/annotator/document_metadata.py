"""Fast PubMed-only document metadata lookups."""

import asyncio
import os
from typing import Dict, Iterable, List, Optional, Tuple

from biothings_annotator.annotator.settings import DOCUMENT_METADATA_REQUEST_TIMEOUT, ELASTICSEARCH_CONNECTION
from biothings_annotator.annotator.utils import get_elasticsearch_client


PUBMED_SOURCE_FIELDS = ["pubmed"]
PUBMED_IDENTIFIER_SCOPES = ["pubmed.identifiers"]
PMID_PREFIX = "PMID"
# Used only by the numeric pub_date fallback. The verbatim pubdate_raw path
# already carries PubMed's own three-letter abbreviations.
MONTH_ABBREVIATIONS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _is_document_id(publication_id: str) -> bool:
    """A PMID is the index's document ``_id``; every other prefix needs a search."""
    return publication_id.split(":", 1)[0].upper() == PMID_PREFIX


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
    if not parts or len(parts[0]) != 4 or not parts[0].isdigit():
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
    """
    year, month, day = _raw_publication_date_components(metadata.get("pubdate_raw"))
    if year:
        return year, month, day
    return _iso_publication_date_components(metadata.get("pub_date"))


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


class DocumentMetadataService:
    """Retrieve only PubMed metadata from the dedicated Elasticsearch alias."""

    def __init__(
        self,
        elasticsearch_connection: Optional[str] = None,
        request_timeout: Optional[float] = None,
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

    async def get_publications(self, publication_ids: Iterable[str]) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
        """Return ordered publication results and missing identifiers."""
        publication_ids = list(publication_ids)
        if not publication_ids:
            return {}, []

        document_ids = [publication_id for publication_id in publication_ids if _is_document_id(publication_id)]
        search_ids = [publication_id for publication_id in publication_ids if not _is_document_id(publication_id)]

        client = get_elasticsearch_client("pubmed", self.elasticsearch_connection)
        hits_by_id = await asyncio.wait_for(
            self._fetch_hits(client, document_ids, search_ids),
            timeout=self.request_timeout,
        )

        results: Dict[str, Dict[str, str]] = {}
        not_found: List[str] = []
        for publication_id in publication_ids:
            metadata = hits_by_id.get(publication_id, {}).get("pubmed")
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

