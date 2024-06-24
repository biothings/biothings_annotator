"""
Translator Node Annotator Service Handler
"""

import logging
import json

import tornado
from tornado.web import HTTPError

from biothings_annotator.annotator import Annotator

logger = logging.getLogger(__name__)


class AnnotatorHandler(tornado.web.RequestHandler):
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

    async def get(self, *args, **kwargs):
        annotator = Annotator()
        curie = args[0] if args else None
        if curie:
            try:
                annotated_node = annotator.annotate_curie(
                    curie, raw=self.args.raw, fields=self.args.fields
                )
            except ValueError as e:
                raise HTTPError(400, reason=repr(e))
            self.finish(annotated_node)
        else:
            raise HTTPError(404, reason="missing required input curie id")

    async def post(self, *args, **kwargs):
        annotator = Annotator()
        try:
            annotated_node_d = annotator.annotate_trapi(
                json.loads(self.request.body.decode()),
                append=False,
                raw=False,
                fields=self.request.query.split("=")[1],
                limit=None
            )
        except ValueError as e:
            raise HTTPError(400, reason=repr(e))
        self.finish(annotated_node_d)
