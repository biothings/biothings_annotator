"""
Translator Node Annotator Service Handler translated to sanic
"""

import logging

import sanic
from sanic.views import HTTPMethodView
from sanic.exceptions import SanicException
from sanic.request import Request

from biothings_annotator.annotator import Annotator

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
        except ValueError as value_err:
            raise SanicException(status_code=400, message=repr(value_err)) from value_err


class BatchCurieView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    async def post(self, request: Request):
        fields = request.args.get("fields", None)
        raw = request.args.get("raw", False)
        include_extra = request.args.get("include_extra", True)

        annotator = Annotator()
        batch_curie = request.json
        try:
            annotated_node = annotator.annotate_curie_list(
                batch_curie, fields=fields, raw=raw, include_extra=include_extra
            )
            return sanic.json(annotated_node, headers=self.default_headers)
        except ValueError as value_err:
            raise SanicException(status_code=400, message=repr(value_err)) from value_err


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
        except ValueError as value_err:
            raise SanicException(status_code=400, message=repr(value_err)) from value_err
