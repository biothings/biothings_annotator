"""Fast PubMed-only document metadata lookups."""

import asyncio
import os
from typing import Dict, Iterable, List, Optional, Tuple

from biothings_annotator.annotator.settings import DOCUMENT_METADATA_REQUEST_TIMEOUT, ELASTICSEARCH_CONNECTION
from biothings_annotator.annotator.utils import get_elasticsearch_client


PUBMED_SOURCE_FIELDS = ["pubmed"]
MONTH_ABBREVIATIONS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _publication_date_components(publication_date: object) -> Tuple[str, str, str]:
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


def format_publication_metadata(metadata: Dict) -> Dict[str, str]:
    """Translate the compact indexed PubMed object into the legacy field names."""
    journal = metadata.get("journal")
    if not isinstance(journal, dict):
        journal = {}
    publication_year, publication_month, publication_day = _publication_date_components(
        metadata.get("pub_date")
    )

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

    async def get_publications(self, pubmed_ids: Iterable[str]) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
        """Return ordered publication results and missing identifiers."""
        pubmed_ids = list(pubmed_ids)
        if not pubmed_ids:
            return {}, []

        client = get_elasticsearch_client("pubmed", self.elasticsearch_connection)
        hits = await asyncio.wait_for(
            client.mget(pubmed_ids, fields=PUBMED_SOURCE_FIELDS),
            timeout=self.request_timeout,
        )

        results: Dict[str, Dict[str, str]] = {}
        not_found: List[str] = []
        for pubmed_id, hit in zip(pubmed_ids, hits):
            metadata = hit.get("pubmed")
            if hit.get("notfound") or not isinstance(metadata, dict):
                not_found.append(pubmed_id)
                continue
            results[pubmed_id] = format_publication_metadata(metadata)
        return results, not_found
