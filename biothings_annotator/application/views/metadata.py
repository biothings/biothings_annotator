"""
Metadata routes
"""

import functools
import logging
from typing import Union

import sanic
from sanic import json, text, Sanic
from sanic.views import HTTPMethodView
from sanic.request import Request
from sanic_ext import openapi
import yaml

from sanic_ext.extensions.openapi.builders import SpecificationBuilder
from sanic_ext.extensions.openapi.definitions import PathItem, Operation


logger = logging.getLogger(__name__)


def _build_paths(spec_instance: SpecificationBuilder, app: Sanic) -> dict:
    """
    Override this to force the building to be taken care of here where we can
    control the building process
    """

    def _build_operation(value) -> PathItem:
        defined_mapping = value.__dict__.copy()
        autodoc_mapping = value._autodoc or {}
        default_mapping = value._default

        operation_mapping = {}

        for mapping in (default_mapping, defined_mapping, autodoc_mapping):
            pruned_mapping = {k: v for k, v in mapping.items() if v and not k.startswith("_")}
            operation_mapping.update(pruned_mapping)

        if "responses" not in operation_mapping:
            operation_mapping["responses"] = {"default": {"description": "OK"}}

        operation_instance = Operation(**operation_mapping)
        return operation_instance

    paths = {}
    for path, operations in spec_instance._paths.items():
        paths[path] = PathItem(
            **{
                k: v if isinstance(v, dict) else _build_operation(v)
                for k, v in operations.items()
                if isinstance(v, dict) or v._app is app
            }
        )

    return paths


class MetadataView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def get(self, request: Request) -> Union[text, json]:
        """
        openapi:
        ---
        summary: Generates the auto-documented OpenAPI specification dynamically from the annotator application
        responses:
          '200':
            description: Successful generation of the OpenAPI auto-generated documentation in yaml format
            content:
              text/plain:
                schema:
                  type: string
          '400':
            description: Error occured during auto-generation of the OpenAPI documentation
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    endpoint:
                      type: string
                    message:
                      type: string
                    exception:
                      type: string
        """
        try:
            specification_builder = SpecificationBuilder()
            specification_builder._build_paths = functools.partial(_build_paths, specification_builder)
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


class VersionView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    def open_version_file(self):
        with open("version.txt", "r") as version_file:
            version = version_file.read().strip()
            return version

    async def get(self, _: Request):
        """
        openapi:
        ---
        summary: Checks the version of the annotator service
        responses:
          '200':
            description: Successful github commit hash generation
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    version:
                      type: string
        """
        try:
            version = "Unknown"

            try:
                version = self.open_version_file()
            except FileNotFoundError:
                logger.error("The version.txt file does not exist.")
            except Exception as exc:
                logger.error(f"Error getting GitHub commit hash from version.txt file: {exc}")

            result = {"version": version}
            return sanic.json(result, headers=self.default_headers)

        except Exception as exc:
            logger.error(f"Error getting GitHub commit hash: {exc}")
            result = {"version": "Unknown"}
            return sanic.json(result)
