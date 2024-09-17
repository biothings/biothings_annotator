"""
Contains the forced target factory for the sanic application
"""

import logging

from sanic import Sanic

from biothings_annotator.application.views import build_routes
from biothings_annotator.application.middleware import build_middleware
from biothings_annotator.application.exceptions import build_exception_handers

logging.basicConfig()
logger = logging.getLogger("sanic-application")
logger.setLevel(logging.DEBUG)


def build_application(configuration: dict = None) -> Sanic:
    """
    Generates and returns an instance of the sanic.app.Sanic application
    for the web server

    The sanic.web.Sanic application has the following constructor:
    https://sanic.dev/api/sanic.app.html#getting-started
    class Sanic(
        name: str,
        config: Optional[config_type] = None,
        ctx: Optional[ctx_type] = None,
        router: Optional[Router] = None,
        signal_router: Optional[SignalRouter] = None,
        error_handler: Optional[ErrorHandler] = None,
        env_prefix: Optional[str] = SANIC_,
        request_class: Optional[Type[Request]] = None,
        strict_slashes: bool = False,
        log_config: Optional[Dict[str, Any]] = None,
        configure_logging: bool = True,
        dumps: Optional[Callable[..., AnyStr]] = None,
        loads: Optional[Callable[..., Any]] = None,
        inspector: bool = False,
        inspector_class: Optional[Type[Inspector]] = None,
        certloader_class: Optional[Type[CertLoader]] = None
    )

    Loads the following additional aspects for the webserver:
    > routes
    > middleware
    > exception handlers
    """
    application_configuration = configuration["application"]["configuration"]
    extension_configuration = configuration["application"]["extension"]

    configuration_settings = {}
    configuration_settings.update(application_configuration)
    configuration_settings.update(extension_configuration["openapi"])
    configuration_settings.update(extension_configuration["cors"])

    application = Sanic(name="biothings-annotator")
    application.update_config(configuration_settings)

    application_routes = build_routes()
    for route in application_routes:
        try:
            application.add_route(**route)
        except Exception as gen_exc:
            logger.exception(gen_exc)
            logger.error("Unable to add route %s", route)
            raise gen_exc

    application_middleware = build_middleware()
    for middleware in application_middleware:
        try:
            application.register_middleware(**middleware)
        except Exception as gen_exc:
            logger.exception(gen_exc)
            logger.error("Unable to add middleware %s", middleware)
            raise gen_exc

    exception_handlers = build_exception_handers()
    for exception_handler in exception_handlers:
        try:
            application.error_handler.add(**exception_handler)
        except Exception as gen_exc:
            logger.exception(gen_exc)
            logger.error("Unable to add exception handler %s", exception_handler)
            raise gen_exc

    return application
