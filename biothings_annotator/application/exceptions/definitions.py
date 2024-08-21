"""
Exception handling for the application level
"""

import logging
import operator

import sanic
from sanic.exceptions import SanicException
from sanic.request import Request

from biothings_annotator.application.views import build_routes

logger = logging.getLogger(__name__)


class RoutingException(SanicException):
    """
    Used for displaying information an HTTP 405 has
    occured and sanic produces a MethodNotAllowed exception
    to provide information about our path routing
    """

    def __init__(self, request: Request, exception: SanicException):
        potential_routes = self._evaluate_path(request=request)
        formatted_routes = "> " + "> ".join(potential_routes)
        message = "Router was unable to find a valid route. " f"Potential routes: {formatted_routes}"
        status_code = 400
        super().__init__(message=message, status_code=status_code, quiet=False)

    def _evaluate_path(self, request: Request) -> list[str]:
        """
        Determines if any additional information related to the uri path
        can be useful
        """
        request_method = request.method

        application_context = sanic.Sanic.get_app()
        router = application_context.router

        similar_method_routes = []
        for route in router.routes:
            if request_method in route.methods:
                similar_method_routes.append(route)

        route_uri = [f"/{route.path}" for route in similar_method_routes]
        return route_uri
