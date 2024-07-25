from .compression import compress_response


def build_middleware() -> list[dict]:
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
    compression_middleware = {"middleware": compress_response, "attach_to": "response"}
    middleware_collection = [compression_middleware]
    return middleware_collection
