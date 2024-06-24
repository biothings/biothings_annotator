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


class AnnotatorView(HTTPMethodView):
    async def get(self, request: Request, curie: str):
        fields = request.args.get("fields", None)
        raw = request.args.get("raw", False)

        annotator = Annotator()
        try:
            annotated_node = annotator.annotate_curie(
                curie, fields=fields, raw=raw
            )
            return sanic.json(annotated_node)
        except ValueError as value_err:
            raise SanicException(
                status_code=400, message=repr(value_err)
            ) from value_err

    async def post(self, request: Request):
        fields = request.args.get("fields", None)
        raw = request.args.get("raw", False)
        append = request.args.get("append", False)
        limit = request.args.get("limit", None)

        annotator = Annotator()
        try:
            annotated_node_d = annotator.annotate_trapi(
                request.json,
                fields=fields,
                raw=raw,
                append=append,
                limit=limit,
            )
            return sanic.json(annotated_node_d)
        except ValueError as value_err:
            raise SanicException(
                status_code=400, message=repr(value_err)
            ) from value_err
