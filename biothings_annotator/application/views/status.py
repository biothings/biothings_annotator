import json
import logging
from functools import lru_cache

import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.annotator import Annotator
from biothings_annotator.application.status_health import HEALTH_ERROR_MESSAGE, get_status_health
from biothings_annotator.application.status_metadata import get_backend_metadata
from biothings_annotator.application.structure import DOCKER_WEB_APP_DIRECTORY, WEB_APP_DIRECTORY


logger = logging.getLogger(__name__)


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
        status, _error = await get_status_health(request.app, Annotator())
        return sanic.json(None, headers=self.default_headers, status=status)

    async def get(self, request: Request):
        """
        Report cached health and independently refreshed source metadata.

        Uses a singular CURIE (NCBIGene:1017) for annotation to verify
        that we can still access the underlying biothings infrastructure
        to provide the annotation.
        """
        try:
            annotator = Annotator()
            status, error = await get_status_health(request.app, annotator)
            if status != 200:
                return sanic.json({"success": False, "error": error}, headers=self.default_headers, status=status)

            result = {
                "status": "running",
                "deployment_environment": request.app.config.DEPLOYMENT_ENVIRONMENT,
                "version": get_openapi_version(),
                "query_backend": annotator.query_backend,
                "available_query_backends": await get_backend_metadata(request.app, annotator),
            }
            return sanic.json(result, headers=self.default_headers, status=200)
        except Exception:
            logger.exception("Unable to report service status")
            result = {"success": False, "error": HEALTH_ERROR_MESSAGE}
            return sanic.json(result, headers=self.default_headers, status=400)
