from typing import Dict, List

from biothings_annotator.annotator.settings import (
    BIOLINK_PREFIX_to_BioThings,
    QUERY_BACKEND_ALIASES,
    SUPPORTED_QUERY_BACKENDS,
)


class InvalidQueryBackendError(ValueError):
    def __init__(self, requested_value):
        self.requested_value = requested_value
        self.aliases = dict(QUERY_BACKEND_ALIASES)
        self.supported_values = list(SUPPORTED_QUERY_BACKENDS) + list(self.aliases)
        self.message = "Unsupported query backend. Use one of the supported query backend values."
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
