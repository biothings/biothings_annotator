from .annotator import AnnotatorView


def build_routes() -> list[dict]:
    """
    Basic method for aggregating all of the views created
    for the annotator service

    This builds the arguments to be passed to
    https://sanic.dev/api/sanic.app.html#sanic-app-sanic-addroute

    For the moment however, we're only targetting adding the handler
    and uri argument for simplicity
    """
    annotator_route = {"handler": AnnotatorView.as_view(), "uri": r"/annotator/([^/]+)"}
    route_collection = [annotator_route]
    return route_collection
