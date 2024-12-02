from typing import Dict, List

from .sentry import initialize_sentry


def build_listeners() -> List[Dict]:
    """
    Basic method for aggregating all of listeners created
    for the annotator service
    """
    sentry_listener = {"listener": initialize_sentry, "event": "before_server_start", "priority": 0}
    listener_collection = [sentry_listener]
    return listener_collection
