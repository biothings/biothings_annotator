"""
Metadata routes
"""

from typing import Union

from sanic import json, text
from sanic.request import Request
import yaml

from sanic_ext.extensions.openapi.builders import SpecificationBuilder


async def metadata(request: Request) -> Union[text, json]:
    """
    openapi:
    ---
    summary: Generates the auto-documented OpenAPI specification dynamically from the annotator application
    responses:
      '200':
        description: A successful network status check
        content:
          application/json:
      '400':
        description: An unsuccessful network status check
    """
    try:
        specification_builder = SpecificationBuilder()
        openapi_definition = specification_builder.build(request.app)
        openapi_mapping = openapi_definition.serialize()
        text_response = text(yaml.dump(openapi_mapping))
        return text_response
    except Exception as exc:
        error_context = {
            "endpoint": "/metadata/",
            "message": "Unknown exception occured",
            "exception": repr(exc),
        }
        general_error_response = json(error_context, status=400)
        return general_error_response
