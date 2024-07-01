"""
Default helper route for viewing options when passed as /
"""

import logging
import urllib

from sanic import Sanic
from sanic.request import Request
from sanic.response import json
from sanic.views import HTTPMethodView

from biothings_annotator.annotator import Annotator

logger = logging.getLogger(__name__)


class DefaultView(HTTPMethodView):
    async def get(self, request: Request) -> json:
        application_context = Sanic.get_app()
        router = application_context.router

        route_maps = {}
        for route in router.routes:
            route_maps[str(route.name)] = urllib.parse.unquote(route.path)

        return json(route_maps)
