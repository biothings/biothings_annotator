"""
Exception handling for the application level
"""

import sanic
from sanic.exceptions import MethodNotAllowed
from sanic.request import Request

from biothings_annotator.application.exceptions.definitions import RoutingHelperException


async def handle_route_not_found(request: Request, exception: MethodNotAllowed) -> RoutingHelperException:
    """
    Handler for exceptions in the case where the route / path provided was not
    found by the application
    """
    exception_instance = RoutingHelperException(request=request, exception=exception)
    return exception_instance
