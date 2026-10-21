"""
Metadata routes
"""

import logging

import sanic
from sanic import json
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.annotator import Annotator

logger = logging.getLogger(__name__)


class VersionView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.is_local = application.config.get("DEPLOYMENT_ENVIRONMENT") == "local"
        self.local_git_version = getattr(application.ctx, "local_git_version", "Unknown")
        self.default_headers = {"Cache-Control": "no-store" if self.is_local else f"max-age={cache}, public"}

    def open_version_file(self):
        with open("version.txt", "r") as version_file:
            version = version_file.read().strip()
            return version

    def build_response_body(self, version: str):
        annotator = Annotator()
        result = {
            "version": version,
            "query_backend": annotator.query_backend,
        }
        if annotator.query_backend == "elasticsearch":
            result["elasticsearch_connection"] = annotator.elasticsearch_connection
        return result

    async def get(self, _: Request) -> json:
        """
        API versioning endpoint

        Leverages extracting a github commit hash from the annotator
        repository as the version to check the commit HEAD.
        Allows for verifying what the latest commit is on the live instance

        For local deployments, a missing version file uses the startup Git snapshot.
        Otherwise, an unreadable version file reports "Unknown".
        """
        try:
            version = "Unknown"

            try:
                version = self.open_version_file()
            except FileNotFoundError:
                if self.is_local:
                    version = self.local_git_version
                else:
                    logger.error("The version.txt file does not exist.")
            except Exception as exc:
                logger.error(f"Error getting GitHub commit hash from version.txt file: {exc}")

            result = self.build_response_body(version)
            return sanic.json(result, headers=self.default_headers)

        except Exception as exc:
            logger.error(f"Error getting GitHub commit hash: {exc}")
            result = self.build_response_body("Unknown")
            return sanic.json(result, headers=self.default_headers)
