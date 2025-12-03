import logging

import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.annotator import Annotator
from biothings_annotator.annotator.exceptions import TRAPIInputError

logger = logging.getLogger(__name__)


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
