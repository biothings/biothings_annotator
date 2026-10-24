import json
from functools import lru_cache

import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.annotator import Annotator
from biothings_annotator.application.status_metadata import get_backend_metadata
from biothings_annotator.application.structure import DOCKER_WEB_APP_DIRECTORY, WEB_APP_DIRECTORY


@lru_cache(maxsize=None)
def get_openapi_version() -> str:
    """Read the API version from the OpenAPI specification served by this deployment."""
    web_app_directory = DOCKER_WEB_APP_DIRECTORY if DOCKER_WEB_APP_DIRECTORY.exists() else WEB_APP_DIRECTORY
    specification = json.loads(web_app_directory.joinpath("openapi.json").read_text(encoding="utf-8"))
    return specification["info"]["version"]


class StatusView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        self.default_headers = {"Cache-Control": "no-store"}

    async def head(self, request: Request):
        curie = "NCBIGene:1017"
        fields = "_id"

        annotator = Annotator()
        try:
            annotated_node = await annotator.annotate_curie(curie, fields=fields, raw=True, include_extra=False)

            if "NCBIGene:1017" not in annotated_node:
                return sanic.json(None, headers=self.default_headers, status=500)

            return sanic.json(None, headers=self.default_headers, status=200)
        except Exception:
            return sanic.json(None, headers=self.default_headers, status=400)

    async def get(self, request: Request):
        """
        Report service status and release metadata after a live annotation check.

        Uses a singular CURIE (NCBIGene:1017) for annotation to verify
        that we can still access the underlying biothings infrastructure
        to provide the annotation.
        """
        curie = "NCBIGene:1017"
        fields = "_id"

        annotator = Annotator()
        try:
            annotated_node = await annotator.annotate_curie(curie, fields=fields, raw=True, include_extra=False)

            if "NCBIGene:1017" not in annotated_node:
                result = {"success": False, "error": "Service unavailable due to a failed data check!"}
                return sanic.json(result, headers=self.default_headers, status=500)

            result = {
                "status": "running",
                "deployment_environment": request.app.config.DEPLOYMENT_ENVIRONMENT,
                "version": get_openapi_version(),
                "query_backend": annotator.query_backend,
                "available_query_backends": await get_backend_metadata(request.app, annotator),
            }
            return sanic.json(result, headers=self.default_headers, status=200)
        except Exception as exc:
            result = {"success": False, "error": repr(exc)}
            return sanic.json(result, headers=self.default_headers, status=400)
