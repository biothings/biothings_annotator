from typing import Dict, List, Optional

from biothings_annotator.annotator.settings import (
    QUERY_BACKEND_ALIASES,
    SUPPORTED_QUERY_BACKENDS,
    BIOLINK_PREFIX_to_BioThings,
)


class InvalidQueryBackendError(ValueError):
    def __init__(self, requested_value):
        self.requested_value = requested_value
        self.aliases = dict(QUERY_BACKEND_ALIASES)
        self.supported_values = list(SUPPORTED_QUERY_BACKENDS) + list(self.aliases)
        self.message = "Unsupported query backend. Use one of the supported query backend values."
        super().__init__(self.message)


class BackendVerificationError(RuntimeError):
    """Report why a live check of the configured query backend failed."""

    _MESSAGES = {
        "unsupported_backend": "Live backend verification is only available for Elasticsearch instances.",
        "configuration_error": "Unable to resolve the configured Elasticsearch connection.",
        "connection_error": "Unable to connect to the configured Elasticsearch backend.",
        "authentication_error": "The Elasticsearch backend rejected the verification request.",
        "http_error": "The Elasticsearch backend verification request failed.",
        "invalid_response": "The Elasticsearch backend returned an invalid server information response.",
    }

    def __init__(self, query_backend: str, reason: str, status_code: Optional[int] = None):
        self.query_backend = query_backend
        self.reason = reason
        self.status_code = status_code
        self.message = self._MESSAGES.get(reason, "Unable to verify the configured query backend.")
        super().__init__(self.message)


class SourceDiscoveryError(RuntimeError):
    def __init__(self, source=None):
        self.source = source
        self.message = "Unable to determine BioThings source availability."
        super().__init__(self.message)


class TRAPIInputError(ValueError):
    def __init__(self, trapi_input: Dict):
        self.input_structure = trapi_input
        self.expected_structure = {"message": {"knowledge_graph": {"nodes": {"node0": {}, "node1": {}, "nodeN": {}}}}}
        self.message = "Unsupported TRAPI input structure"
        super().__init__()


class InvalidCurieError(ValueError):
    def __init__(self, curie: str):
        self.supported_biolink_nodes = InvalidCurieError.annotator_supported_nodes()
        self.message = f"Unsupported CURIE id: {curie}. "
        if ":" not in curie:
            self.message += "Invalid structure for the provided CURIE id. Expected form <node>:<id>"
        super().__init__()

    @staticmethod
    def annotator_supported_nodes() -> List:
        """
        Returns the list of supported nodes in the annotator service
        based off the biolink prefix
        """
        return list(BIOLINK_PREFIX_to_BioThings.keys())
