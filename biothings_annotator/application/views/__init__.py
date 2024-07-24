from .annotator import CurieView, TrapiView


def build_routes() -> list[dict]:
    """
    Basic method for aggregating all of the views created
    for the annotator service

    This builds the arguments to be passed to
    https://sanic.dev/api/sanic.app.html#sanic-app-sanic-addroute

    For the moment however, we're only targetting adding the handler
    and uri argument for simplicity
    """
    curie_route = {"handler": CurieView.as_view(), "uri": r"/<curie:str>", "name": "curie_endpoint"}
    curie_route_mirror = {
        "handler": CurieView.as_view(),
        "uri": r"/annotator/<curie:str>",
        "name": "curie_endpoint_mirror",
    }
    trapi_route = {"handler": TrapiView.as_view(), "uri": "/", "name": "trapi_endpoint"}
    trapi_route_mirror = {"handler": TrapiView.as_view(), "uri": "/annotator/", "name": "trapi_endpoint_mirror"}
    route_collection = [curie_route, curie_route_mirror, trapi_route, trapi_route_mirror]
    return route_collection
