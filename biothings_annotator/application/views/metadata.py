"""
Metadata routes
"""

import tempfile

from sanic import file, text
from sanic.request import Request
import yaml

from sanic_ext.extensions.openapi.builders import SpecificationBuilder


async def metadata(request: Request) -> text:
    """
    Generates the auto-documented OpenAPI specification
    from the application using the sanic-ext openapi module
    """
    specification_builder = SpecificationBuilder()
    openapi_definition = specification_builder.build(request.app)
    openapi_mapping = openapi_definition.serialize()
    text_response = text(yaml.dump(openapi_mapping))
    return text_response


async def metadata_file(request: Request) -> file:
    """
    Generates the auto-documented OpenAPI specification
    from the application using the sanic-ext openapi module

    Then returns that as a static file
    """
    metadata_content = await metadata(request)
    with tempfile.NamedTemporaryFile() as temp_file_handle:
        temp_file_handle.write(metadata_content.body)
        temp_file_handle.flush()
        file_response = await file(temp_file_handle.name)
        return file_response
