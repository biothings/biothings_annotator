from .annotator import AnnotatorView
from .default import DefaultView


def build_routes() -> list[dict]:
    """
    Basic method for aggregating all of the views created
    for the annotator service

    This builds the arguments to be passed to
    https://sanic.dev/api/sanic.app.html#sanic-app-sanic-addroute

    For the moment however, we're only targetting adding the handler
    and uri argument for simplicity
    """
    annotator_route = {"handler": AnnotatorView.as_view(), "uri": r"/annotator/<curie:str>"}
    default_route = {"handler": DefaultView.as_view(), "uri": "/"}
    route_collection = [annotator_route, default_route]
    return route_collection
