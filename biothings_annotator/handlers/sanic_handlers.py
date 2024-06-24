"""
Handler for the sanic specific web server
"""

import logging

import sanic
from sanic import json
from sanic.views import HTTPMethodView
from sanic.exceptions import BadRequest

from biothings_annotator import Annotator


logger = logging.getLogger(__name__)


name = "annotator"
kwargs = {
    "*": {
        "raw": {"type": bool, "default": False},
        "fields": {"type": str, "default": None},
    },
    "POST": {
        # If True, append annotations to existing "attributes" field
        "append": {"type": bool, "default": False},
        # If set, limit the number of nodes to annotate
        "limit": {"type": int, "default": None},
    },
}


class AnnotatorView(HTTPMethodView):

    async def get(self, request: sanic.request.Request, query: str):
        annotator = Annotator()
        try:
            # annotated_node = annotator.annotate_curie(query, raw=self.args.raw, fields=self.args.fields)
            annotated_node = annotator.annotate_curie(query)
        except ValueError as value_err:
            logger.exception(value_err)
            message = f"Unknown error while annotating the following curie query: [{curie}]"
            context = {"curie": curie, "raw": self.args.raw, "fields": self.args.fields}
            sanic_bad_request = BadRequest(message=message, quiet=False, context=context)
            raise sanic_bad_request from value_err

        logger.debug("Annotator Node: %s", annotated_node)
        return json(annotated_node)

    # async def post(self, request):
    #     annotator = Annotator()
    #     try:
    #         annotated_node_d = annotator.annotate_trapi(
    #             self.args_json,
    #             append=self.args.append,
    #             raw=self.args.raw,
    #             fields=self.args.fields,
    #             limit=self.args.limit,
    #         )
    #     except ValueError as e:
    #         raise HTTPError(400, reason=repr(e))
    #     self.finish(annotated_node_d)
