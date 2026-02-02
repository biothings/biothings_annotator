import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.annotator import Annotator


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
        Network status validation endpoint

        Uses a singular CURIE (NCBIGene:1017) for annotation to verify
        that we can still access the underlying biothings infrastructure
        to provide the annoatation
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
