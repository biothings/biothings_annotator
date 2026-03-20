from typing import Dict, List
from biothings_annotator.application.views.curie import CurieView
from biothings_annotator.application.views.metadata import VersionView
from biothings_annotator.application.views.status import StatusView
from biothings_annotator.application.views.trapi import TrapiView


def build_routes() -> List[Dict]:
    """
    Basic method for aggregating all of the views created
    for the annotator service

    This builds the arguments to be passed to
    https://sanic.dev/api/sanic.app.html#sanic-app-sanic-addroute

    For the moment however, we're only adding the handler
    and uri argument for simplicity
    """

    # --- STATUS ROUTE ---
    status_route = {
        "handler": StatusView.as_view(),
        "uri": r"/status",
        "name": "status_endpoint",
    }

    # --- CURIE ROUTES ---
    curie_route_get = {
        "handler": CurieView.as_view(),
        "uri": r"/curie/<curie:str>",
        "name": "curie_endpoint",
        "methods": ["GET"],
    }

    curie_route_post = {
        "handler": CurieView.as_view(),
        "uri": r"/curie/",
        "name": "batch_curie_endpoint",
        "methods": ["POST"],
    }

    # --- TRAPI ROUTES ---
    trapi_route = {"handler": TrapiView.as_view(), "uri": "/trapi/", "name": "trapi_endpoint"}

    # --- METADATA ROUTES ---
    version_route = {
        "handler": VersionView.as_view(),
        "uri": r"/version",
        "name": "version_endpoint",
    }

    route_collection = [
        curie_route_get,
        curie_route_post,
        trapi_route,
        status_route,
        version_route,
    ]
    return route_collection
