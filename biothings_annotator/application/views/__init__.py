from typing import Dict, List
from biothings_annotator.application.views.annotator import (
    BatchCurieView,
    CurieView,
    StatusView,
    TrapiView,
)
from biothings_annotator.application.views.metadata import MetadataView, VersionView


def build_routes() -> List[Dict]:
    """
    Basic method for aggregating all of the views created
    for the annotator service

    This builds the arguments to be passed to
    https://sanic.dev/api/sanic.app.html#sanic-app-sanic-addroute

    For the moment however, we're only targetting adding the handler
    and uri argument for simplicity
    """

    # --- STATUS ROUTE ---
    status_route_main = {
        "handler": StatusView.as_view(),
        "uri": r"/status",
        "name": "status_endpoint",
    }

    # --- CURIE ROUTES ---
    curie_route_main = {
        "handler": CurieView.as_view(),
        "uri": r"/curie/<curie:str>",
        "name": "curie_endpoint",
    }

    batch_curie_route = {
        "handler": BatchCurieView.as_view(),
        "uri": r"/curie/",
        "name": "batch_curie_endpoint",
    }

    # --- TRAPI ROUTES ---
    trapi_route_main = {"handler": TrapiView.as_view(), "uri": "/trapi/", "name": "trapi_endpoint"}

    # --- METADATA ROUTES ---
    metadata_route = {"handler": MetadataView.as_view(), "uri": "/metadata/openapi", "name": "metadata"}

    version_route_main = {
        "handler": VersionView.as_view(),
        "uri": r"/version",
        "name": "version_endpoint",
    }

    route_collection = [
        status_route_main,
        version_route_main,
        curie_route_main,
        batch_curie_route,
        trapi_route_main,
        metadata_route,
    ]
    return route_collection
