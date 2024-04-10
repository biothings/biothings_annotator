"""
Handler for the tornado specific web server
"""
from biothings.web.handlers import BaseAPIHandler

from tornado.web import HTTPError, RequestHandler

from biothings_annotator import Annotator

class AnnotatorHandler(RequestHandler):
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
                # annotated_node = annotator.annotate_curie(curie, raw=self.args.raw, fields=self.args.fields)
                annotated_node = annotator.annotate_curie(curie)
            except ValueError as e:
                raise HTTPError(400, reason=repr(e)) from e
            self.finish(annotated_node)
        else:
            raise HTTPError(400, reason="missing required input curie id")

    async def post(self, *args, **kwargs):
        annotator = Annotator()
        try:
            annotated_node_d = annotator.annotate_trapi(
                self.args_json,
                append=self.args.append,
                raw=self.args.raw,
                fields=self.args.fields,
                limit=self.args.limit,
            )
        except ValueError as e:
            raise HTTPError(400, reason=repr(e))
        self.finish(annotated_node_d)
