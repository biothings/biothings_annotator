from typing import Dict, List


def build_middleware() -> List[Dict]:
    """
    Basic method for aggregating all of middleware created
    for the annotator service

    Targets the register_middleware method with the following structure:
    def register_middleware(
        self,
        middleware: Union[MiddlewareType, Middleware],
        attach_to: str = "request",
        *,
        priority: Union[Default, int] = _default,
    ) -> Union[MiddlewareType, Middleware]:
    """
    middleware_collection = []
    return middleware_collection
