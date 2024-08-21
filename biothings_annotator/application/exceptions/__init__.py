"""
Exception handling for the application level
"""

from sanic.exceptions import MethodNotAllowed

from biothings_annotator.application.exceptions.handlers import handle_method_not_allowed


def build_exception_handers() -> list[dict]:
    """
    Builds the collection of dictionary mappings for the
    handler -> exception map
    """
    method_not_allowed_handler = {"exception": MethodNotAllowed, "handler": handle_method_not_allowed}
    exception_handler_mapping = [method_not_allowed_handler]
    return exception_handler_mapping
