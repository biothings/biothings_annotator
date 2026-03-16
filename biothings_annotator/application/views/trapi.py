import logging
from typing import Optional

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
        fields: Optional[list[str]] = request.args.get("fields", None)
        raw: bool = request.args.get("raw", False)
        append: bool = request.args.get("append", False)
        limit: Optional[int] = int(request.args.get("limit", 0))
        include_extra: bool = request.args.get("include_extra", True)

        annotator = Annotator()
        trapi_body = request.json
        try:
            breakpoint()
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
