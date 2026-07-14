"""
Translator Node Annotator Service Handler translated to sanic
"""

import logging
import json
import urllib.parse

import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.annotator import Annotator
from biothings_annotator.annotator.exceptions import InvalidCurieError, InvalidQueryBackendError

logger = logging.getLogger(__name__)


def _query_backend_configuration_error_response():
    logger.error("Invalid query backend deployment configuration")
    return sanic.json(
        {
            "endpoint": "/curie/",
            "message": "Server query backend configuration is invalid.",
        },
        status=500,
    )


class CurieView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def get(self, request: Request, curie: str):
        fields: list[str] = request.args.get("fields", None)
        raw: bool = request.args.get("raw", False)
        include_extra: bool = request.args.get("include_extra", True)
        query_backend = request.args.get("query_backend", None)

        try:
            curie = urllib.parse.unquote(curie, encoding="utf-8", errors="strict")
        except UnicodeError as unicode_err:
            error_context = {
                "input": curie,
                "endpoint": "/curie/",
                "message": "Unicode issue while attempting to process curie",
                "exception": repr(exc),
            }
            unicode_curie_error_response = sanic.json(error_context, status=400)
            return unicode_curie_error_response

        try:
            annotator = Annotator(query_backend=query_backend)
            annotated_node = await annotator.annotate_curie(curie, fields=fields, raw=raw, include_extra=include_extra)
            response_headers = {**self.default_headers, "X-Query-Backend": annotator.query_backend}
            return sanic.json(annotated_node, headers=response_headers)
        except InvalidQueryBackendError:
            return _query_backend_configuration_error_response()
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

    async def post(self, request: Request):
        fields = request.args.get("fields", None)
        raw = request.args.get("raw", False)
        include_extra = request.args.get("include_extra", True)
        query_backend = request.args.get("query_backend", None)
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

        parsed_curie_list = []
        try:
            for curie in curie_list:
                curie = urllib.parse.unquote(curie, encoding="utf-8", errors="strict")
                parsed_curie_list.append(curie)
        except UnicodeError as unicode_err:
            error_context = {
                "input": curie_list,
                "endpoint": "/curie/",
                "message": "Unicode issue while attempting to process curie list",
                "exception": repr(exc),
            }
            unicode_curie_error_response = sanic.json(error_context, status=400)
            return unicode_curie_error_response

        try:
            annotator = Annotator(query_backend=query_backend)
            annotated_node = await annotator.annotate_curie_list(
                curie_list=parsed_curie_list, fields=fields, raw=raw, include_extra=include_extra
            )
            response_headers = {**self.default_headers, "X-Query-Backend": annotator.query_backend}
            return sanic.json(annotated_node, headers=response_headers)
        except InvalidQueryBackendError:
            return _query_backend_configuration_error_response()
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
