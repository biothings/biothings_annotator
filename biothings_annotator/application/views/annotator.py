"""
Translator Node Annotator Service Handler translated to sanic
"""

import logging
import json

import sanic
from sanic.views import HTTPMethodView
from sanic.exceptions import SanicException
from sanic.request import Request
from sanic import response

from biothings_annotator.annotator import Annotator
from biothings_annotator.annotator.exceptions import InvalidCurieError, TRAPIInputError

logger = logging.getLogger(__name__)


class StatusView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def get(self, _: Request):
        curie = "NCBIGene:1017"
        fields = "_id"

        annotator = Annotator()
        try:
            annotated_node = annotator.annotate_curie(curie, fields=fields, raw=False, include_extra=False)

            if "NCBIGene:1017" not in annotated_node:
                result = {"success": False, "error": "Service unavailable due to a failed data check!"}
                return sanic.json(result)

            result = {"success": True}
            return sanic.json(result, headers=self.default_headers)
        except Exception as exc:
            result = {"success": False, "error": repr(exc)}
            return sanic.json(result)


class CurieView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def get(self, request: Request, curie: str):
        fields = request.args.get("fields", None)
        raw = bool(int(request.args.get("raw", 0)))
        include_extra = bool(int(request.args.get("include_extra", 1)))

        annotator = Annotator()

        try:
            annotated_node = annotator.annotate_curie(curie, fields=fields, raw=raw, include_extra=include_extra)
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
        CURIE body supports two forms

        {
            "ids": []
        }

        OR

        [
            ...
        ]
        """
        fields = request.args.get("fields", None)
        raw = request.args.get("raw", False)
        include_extra = request.args.get("include_extra", True)

        annotator = Annotator()
        batch_curie_body = request.json

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
            annotated_node = annotator.annotate_curie_list(
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
        fields = request.args.get("fields", None)
        raw = bool(int(request.args.get("raw", 0)))
        append = bool(int(request.args.get("append", 0)))
        limit = request.args.get("limit", None)
        include_extra = bool(int(request.args.get("include_extra", 1)))

        annotator = Annotator()
        trapi_body = request.json
        try:
            annotated_node = annotator.annotate_trapi(
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
    async def get(self, request: Request, curie: str):
        redirect_response = response.redirect(f"/curie/{curie}", status=302)
        return redirect_response


class TrapiLegacyView(HTTPMethodView):
    async def post(self, request: Request):
        trapi_view = TrapiView()
        redirect_response = await trapi_view.post(request)
        return redirect_response
