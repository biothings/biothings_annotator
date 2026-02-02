from typing import Dict, List, Tuple
from biothings_annotator.application.static.views import StaticFrontendView
from biothings_annotator.application.structure import WEB_APP_DIRECTORY, DOCKER_WEB_APP_DIRECTORY


def build_static_routes() -> List[Dict]:
    """Aggregation method for all of the annotator service static views."""

    # --- FRONTPAGE ROUTE ---
    frontpage_route = {
        "handler": StaticFrontendView.as_view(),
        "uri": "/",
        "name": "frontpage_endpoint",
    }

    route_collection = [frontpage_route]
    return route_collection


def build_static_content() -> List[Tuple]:
    """Aggregation method for all of the annotator service static contents."""
    static_content = []
    if DOCKER_WEB_APP_DIRECTORY.exists():
        static_web_app_content = ("/webapp", DOCKER_WEB_APP_DIRECTORY)  # absolute pathing  # relative pathing
    else:
        static_web_app_content = ("/webapp", WEB_APP_DIRECTORY)  # absolute pathing  # relative pathing

    static_content.append(static_web_app_content)
    return static_content
