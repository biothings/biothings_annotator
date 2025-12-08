"""
Metadata routes
"""

import logging

import sanic
from sanic import json
from sanic.views import HTTPMethodView
from sanic.request import Request


logger = logging.getLogger(__name__)


class VersionView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()
        cache = application.config.CACHE_MAX_AGE
        self.default_headers = {"Cache-Control": f"max-age={cache}, public"}

    def open_version_file(self):
        with open("version.txt", "r") as version_file:
            version = version_file.read().strip()
            return version

    async def get(self, _: Request) -> json:
        """
        API versioning endpoint

        Leverages extracting a github commit hash from the annotator
        repository as the version to check the commit HEAD.
        Allows for verifying what the latest commit is on the live instance

        Will return {"version": "Unknown"} is unable to generate a hash
        """
        try:
            version = "Unknown"

            try:
                version = self.open_version_file()
            except FileNotFoundError:
                logger.error("The version.txt file does not exist.")
            except Exception as exc:
                logger.error(f"Error getting GitHub commit hash from version.txt file: {exc}")

            result = {"version": version}
            return sanic.json(result, headers=self.default_headers)

        except Exception as exc:
            logger.error(f"Error getting GitHub commit hash: {exc}")
            result = {"version": "Unknown"}
            return sanic.json(result)
