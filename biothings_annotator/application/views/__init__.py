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

    ### --- CURIE ROUTES --- ###
    curie_route = {"handler": CurieView.as_view(), "uri": r"/<curie:str>", "name": "curie_endpoint"}
    curie_route_mirror = {
        "handler": CurieView.as_view(),
        "uri": r"/curie/<curie:str>",
        "name": "curie_endpoint_mirror",
    }
    curie_route_legacy = {
        "handler": CurieView.as_view(),
        "uri": r"/annotator/<curie:str>",
        "name": "curie_endpoint_legacy",
    }

    batch_curie_route = {
        "handler": CurieView.as_view(),
        "uri": r"/curie/",
        "name": "batch_curie_endpoint",
    }

    ### --- TRAPI ROUTES --- ###
    trapi_route = {"handler": TrapiView.as_view(), "uri": "/", "name": "trapi_endpoint"}
    trapi_route_mirror = {"handler": TrapiView.as_view(), "uri": "/trapi/", "name": "trapi_endpoint_mirror"}
    trapi_route_legacy = {"handler": TrapiView.as_view(), "uri": "/annotator/", "name": "trapi_endpoint_legacy"}

    route_collection = [
        curie_route,
        curie_route_mirror,
        curie_route_legacy,
        batch_curie_route,
        trapi_route,
        trapi_route_mirror,
        trapi_route_legacy,
    ]
    return route_collection
