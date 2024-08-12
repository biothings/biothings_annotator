from .annotator import BatchCurieView, CurieView, TrapiView


def build_routes() -> list[dict]:
    """
    Basic method for aggregating all of the views created
    for the annotator service

    This builds the arguments to be passed to
    https://sanic.dev/api/sanic.app.html#sanic-app-sanic-addroute

    For the moment however, we're only targetting adding the handler
    and uri argument for simplicity
    """

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

    route_collection = [
        curie_route_main,
        batch_curie_route,
        trapi_route_main,
    ]
    return route_collection
