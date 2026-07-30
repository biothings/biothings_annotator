"""Response headers shared by annotation endpoints."""

from typing import Any, Dict


SKIPPED_CURIE_PREFIXES_HEADER = "X-Skipped-Curie-Prefixes"


def annotation_response_headers(default_headers: Dict[str, str], annotator: Any) -> Dict[str, str]:
    """Add query-backend and optional backend-skip details to response headers."""
    response_headers = {**default_headers, "X-Query-Backend": annotator.query_backend}
    skipped_prefixes = getattr(annotator, "skipped_curie_prefixes", ())
    if isinstance(skipped_prefixes, (list, tuple)) and skipped_prefixes:
        response_headers[SKIPPED_CURIE_PREFIXES_HEADER] = ", ".join(skipped_prefixes)
        response_headers["Cache-Control"] = "no-store"
    return response_headers
