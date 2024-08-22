from biothings_annotator.annotator.settings import BIOLINK_PREFIX_to_BioThings


class TRAPIInputError(ValueError):
    def __init__(self, trapi_input: dict):
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
    def annotator_supported_nodes() -> list:
        """
        Returns the list of supported nodes in the annotator service
        based off the biolink prefix
        """
        return list(BIOLINK_PREFIX_to_BioThings.keys())
