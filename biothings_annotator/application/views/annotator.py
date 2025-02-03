"""
Translator Node Annotator Service Handler translated to sanic
"""

import logging
import json

import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request
from sanic import response
from sanic_ext import openapi

from biothings_annotator.annotator import Annotator
from biothings_annotator.annotator.exceptions import InvalidCurieError, TRAPIInputError

logger = logging.getLogger(__name__)


class StatusView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def head(self, request: Request):
        curie = "NCBIGene:1017"
        fields = "_id"

        annotator = Annotator()
        try:
            annotated_node = await annotator.annotate_curie(curie, fields=fields, raw=False, include_extra=False)

            if "NCBIGene:1017" not in annotated_node:
                return sanic.json(None, status=500)

            return sanic.json(None, headers=self.default_headers, status=200)
        except Exception as exc:
            return sanic.json(None, status=400)

    async def get(self, _: Request):
        """
        openapi:
        ---
        summary: Checks the health status of the annotator service
        responses:
          '200':
            description: A successful network status check
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
          '400':
            description: An unsuccessful network status check
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
                    error:
                      type: string
        """
        curie = "NCBIGene:1017"
        fields = "_id"

        annotator = Annotator()
        try:
            annotated_node = await annotator.annotate_curie(curie, fields=fields, raw=False, include_extra=False)

            if "NCBIGene:1017" not in annotated_node:
                result = {"success": False, "error": "Service unavailable due to a failed data check!"}
                return sanic.json(result, status=500)

            result = {"success": True}
            return sanic.json(result, headers=self.default_headers, status=200)
        except Exception as exc:
            result = {"success": False, "error": repr(exc)}
            return sanic.json(result, status=400)


class CurieView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def get(self, request: Request, curie: str):
        """
        openapi:
        ---
        summary: Retrieve annotation objects based on a CURIE ID
        parameters:
        - name: curie
          in: path
          description: biological identifier using the CURIE format <node>:<id>.
          example: "NCBIGene:695"
          schema:
            type: string
          required: true
        - name: raw
          in: query
          description: 'When true, return annotation fields in their original data structure before transformation. Useful for debugging. Defaults to false'
          required: false
          schema:
            type: boolean
        - name: fields
          in: query
          description: 'Comma-separated fields to override the default set of annotation fields, or passing "fields=all" to return all available fields from the original annotation source. Defaults to none'
          required: false
          schema:
            type: string
        - name: include_extra
          in: query
          description: 'When true, leverage external API(s) data to include additional annotation information in the response. Defaults to true'
          required: false
          schema:
            type: boolean
        responses:
          '200':
            description: A matching annotation object
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    curie:
                      type: object
          '400':
            description: A response indicating an unknown or unsupported curie ID
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    input:
                      type: string
                    message:
                      type: string
                    supported_nodes:
                      type: array
                      items:
                        type: string
                    exception:
                      type: string
        """
        fields = request.args.get("fields", None)
        raw = bool(int(request.args.get("raw", 0)))
        include_extra = bool(int(request.args.get("include_extra", 1)))

        annotator = Annotator()

        try:
            annotated_node = await annotator.annotate_curie(curie, fields=fields, raw=raw, include_extra=include_extra)
            return sanic.json(annotated_node, headers=self.default_headers)
        except InvalidCurieError as curie_err:
            error_context = {
                "input": curie,
                "message": curie_err.message,
                "supported_nodes": curie_err.supported_biolink_nodes,
            }
            curie_error_response = sanic.json(error_context, status=400)
            return curie_error_response
        except Exception as exc:
            error_context = {
                "input": curie,
                "endpoint": "/curie/",
                "message": "Unknown exception occured",
                "exception": repr(exc),
            }
            general_error_response = sanic.json(error_context, status=400)
            return general_error_response


class BatchCurieView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def post(self, request: Request):
        """
        openapi:
        ---
        summary: For a list of curie IDs, return the expanded annotation objects
        parameters:
        - name: raw
          in: query
          description: 'When true, return annotation fields in their original data structure before transformation. Useful for debugging. Defaults to false'
          required: false
          schema:
            type: boolean
        - name: fields
          in: query
          description: 'Comma-separated fields to override the default set of annotation fields, or passing "fields=all" to return all available fields from the original annotation source. Defaults to none'
          required: false
          schema:
            type: string
        - name: include_extra
          in: query
          description: 'When true, leverage external API(s) data to include additional annotation information in the response. Defaults to true'
          required: false
          schema:
            type: boolean
        requestBody:
          content:
            application/json:
              schema:
                properties:
                  ids:
                    description: 'multiple association IDs separated by comma. Note that currently we only take the input ids up to 1000 maximum, the rest will be omitted. Type: string (list). Max: 1000.'
                    type: string
                required:
                - ids
        responses:
          '200':
            description: A list of matching annotation objects
            content:
              application/json:
                schema:
                  type: object
          '400':
            description: A response indicating an improperly formatted query
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    input:
                      type: array
                      items:
                        type: string
                    endpoint:
                      type: string
                    message:
                      type: string
                    supported_nodes:
                      type: array
                      items:
                        type: string
        """
        fields = request.args.get("fields", None)
        raw = request.args.get("raw", False)
        include_extra = request.args.get("include_extra", True)

        annotator = Annotator()
        batch_curie_body = request.json

        curie_list = []
        if isinstance(batch_curie_body, dict):
            curie_list = batch_curie_body.get("ids", [])
        elif isinstance(batch_curie_body, list):
            curie_list = batch_curie_body

        if len(curie_list) == 0:
            body_repr = json.dumps(batch_curie_body)
            message = (
                f"No CURIE ID's found in request body. "
                "Expected format: {'ids': ['id0', 'id1', ... 'idN']} || ['id0', 'id1', ... 'idN']. "
                f"Received request body: {body_repr}"
            )
            error_context = {
                "input": batch_curie_body,
                "endpoint": "/curie/",
                "message": message,
                "supported_nodes": InvalidCurieError.annotator_supported_nodes(),
            }
            curie_error_response = sanic.json(error_context, status=400)
            return curie_error_response

        try:
            annotated_node = await annotator.annotate_curie_list(
                curie_list=curie_list, fields=fields, raw=raw, include_extra=include_extra
            )
            return sanic.json(annotated_node, headers=self.default_headers)

        except InvalidCurieError as curie_err:
            error_context = {
                "input": curie_list,
                "endpoint": "/curie/",
                "message": curie_err.message,
                "supported_nodes": curie_err.supported_biolink_nodes,
            }
            curie_error_response = sanic.json(error_context, status=400)
            return curie_error_response
        except Exception as exc:
            error_context = {
                "input": curie_list,
                "endpoint": "/curie/",
                "message": "Unknown exception occured",
                "exception": repr(exc),
            }
            general_error_response = sanic.json(error_context, status=400)
            return general_error_response


class TrapiView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def post(self, request: Request):
        """
        openapi:
        ---
        summary: Provides an annotated response based off the TRAPI body provided
        parameters:
        - name: append
          in: query
          description: 'When true, append annotations to the existing "attributes" field, otherwise, overwrite the existing "attributes" field. Defaults to false'
          required: false
          schema:
            type: boolean
        - name: raw
          in: query
          description: 'When true, return annotation fields in their original data structure before transformation. Useful for debugging. Defaults to false'
          required: false
          schema:
            type: boolean
        - name: fields
          in: query
          description: 'Comma-separated fields to override the default set of annotation fields, or passing "fields=all" to return all available fields from the original annotation source. Defaults to none'
          required: false
          schema:
            type: string
        - name: include_extra
          in: query
          description: 'When true, leverage external API(s) data to include additional annotation information in the response. Defaults to true'
          required: false
          schema:
            type: boolean
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: object
                    properties:
                      knowledge_graph:
                        type: object
                        properties:
                          nodes:
                            type: object
                          edges:
                            type: object
        responses:
          '200':
            description: A list of matching annotation objects
            content:
              application/json:
                schema:
                  type: object
          '400':
            description: A response indicating an improperly formatted query
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    input:
                      type: object
                      properties:
                        message:
                          type: object
                          properties:
                            knowledge_graph:
                              type: object
                              properties:
                                nodes:
                                  type: object
                                edges:
                                  type: object
                    expected_structure:
                      type: object
                      properties:
                        message:
                          type: object
                          properties:
                            knowledge_graph:
                              type: object
                              properties:
                                nodes:
                                  type: object
                                edges:
                                  type: object
                    endpoint:
                      type: string
                    message:
                      type: string
        """
        fields = request.args.get("fields", None)
        raw = bool(int(request.args.get("raw", 0)))
        append = bool(int(request.args.get("append", 0)))
        limit = request.args.get("limit", None)
        include_extra = bool(int(request.args.get("include_extra", 1)))

        annotator = Annotator()
        trapi_body = request.json
        try:
            annotated_node = await annotator.annotate_trapi(
                trapi_body, fields=fields, raw=raw, append=append, limit=limit, include_extra=include_extra
            )
            return sanic.json(annotated_node, headers=self.default_headers)
        except TRAPIInputError as trapi_input_error:
            error_context = {
                "input": trapi_input_error.input_structure,
                "expected_structure": trapi_input_error.expected_structure,
                "endpoint": "/trapi/",
                "message": trapi_input_error.message,
            }
            trapi_input_error_response = sanic.json(error_context, status=400)
            return trapi_input_error_response
        except Exception as exc:
            error_context = {
                "input": trapi_body,
                "endpoint": "/trapi/",
                "message": "Unknown exception occured",
                "exception": repr(exc),
            }
            general_error_response = sanic.json(error_context, status=400)
            return general_error_response


# --- Legacy Redirects ---
# The /annotator endpoint has been deprcated so we setup these redirects:
# GET /anotator/<CURIE_ID> -> /curie/<CURIE_ID> (Singular CURIE ID)
# POST /anotator/ -> /trapi/
class CurieLegacyView(HTTPMethodView):
    @openapi.deprecated()
    async def get(self, request: Request, curie: str):
        redirect_response = response.redirect(f"/curie/{curie}", status=302)
        return redirect_response


class TrapiLegacyView(HTTPMethodView):
    @openapi.deprecated()
    async def post(self, request: Request):
        trapi_view = TrapiView()
        redirect_response = await trapi_view.post(request)
        return redirect_response
