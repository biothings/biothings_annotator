"""
Exception handling for the application level
"""

import logging

import sanic
from sanic.exceptions import MethodNotAllowed
from sanic.request import Request
from sanic import json

logger = logging.getLogger(__name__)


async def handle_method_not_allowed(request: Request, exception: MethodNotAllowed) -> json:
    """
    Handler for exceptions in the case where the route / path provided was not
    found by the application

    HTTP 405: MethodNotAllowed exception
    """
    method_paths = find_all_paths_by_method(request)
    status_code = 400
    error_mapping = {
        "requestpath": request.path,
        "message": "Router was unable to find a valid route",
        "exception": exception.message,
        "validpaths": method_paths,
    }
    error_response = json(error_mapping, status=status_code)
    return error_response


def find_all_paths_by_method(request: Request) -> list[str]:
    """
    Finds all similar paths based off the method type
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
