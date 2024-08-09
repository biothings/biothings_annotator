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


class RoutingHelperException(SanicException):
    """
    Used for displaying information an HTTP 405 has
    occured and sanic produces a MethodNotAllowed exception
    to provide information about our path routing
    """

    def __init__(self, request: Request, exception: SanicException):
        self._evaluate_path(request=request)
        status_code = 400
        super().__init__(
            message=message, status_code=status_code, quiet=False, context=context, extra=extra, headers=None
        )

    def _evaluate_path(self, request: Request):
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
        alignment = [(RoutingHelperException.string_alignment(request.path, route), route) for route in route_uri]
        return min(alignment, key=operator.itemgetter(0))

    @staticmethod
    def string_alignment(a: str, b: str):
        """
        Compares two strings for alignment using Wagner-Fischer dynamic programming
        algorithm to compute the Damerau–Levenshtein distance
        Implementation comes from the following reference:
        https://en.wikipedia.org/wiki/Damerau%E2%80%93Levenshtein_distance
        used for comparing route uri to determine the most
        similar route upon error to provide user suggestions

        assume that the a is of length m
        assume that the b is of length n
        for all i and j, d[i,j] will hold the Levenshtein distance between
        the first i characters of a and the first j characters of b

        Dimensions:
        a: [1..length(a)] -> 1 indexed
        b: [1..length(b)] -> 1 indexed
        d: [0..length(a), 0..length(b)] -> 0 indexed

        """
        d = [[0 for i in range(len(b) + 1)] for j in range(len(a) + 1)]

        # source prefixes can be transformed into empty string by
        # dropping all characters
        for i in range(0, len(a) + 1):
            d[i][0] = i

        # target prefixes can be reached from empty source prefix
        # by inserting every character
        for j in range(0, len(b) + 1):
            d[0][j] = j

        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                if a[i - 1] == b[j - 1]:
                    substitution_cost = 0
                else:
                    substitution_cost = 1
                d[i][j] = min(
                    (
                        d[i - 1][j] + 1,  # deletion
                        d[i][j - 1] + 1,  # insertion
                        d[i - 1][j - 1] + substitution_cost,  # substitution
                    )
                )
                if i > 1 and j > 1 and b[j - 1] == a[i - 2] and b[j - 2] == a[i - 1]:
                    d[i][j] = min((d[i][j], d[i - 2][j - 2] + 1))  # transposition
        return d[-1][-1]
