from typing import Dict
import logging
import pathlib

from sanic import Sanic

from biothings_annotator.application.views import build_routes
from biothings_annotator.application.middleware import build_middleware
from biothings_annotator.application.exceptions import build_exception_handers

APPLICATION_DIRECTORY = pathlib.Path(__file__).resolve().absolute().parent
CLI_DIRECTORY = APPLICATION_DIRECTORY.joinpath("cli")
CONFIGURATION_DIRECTORY = APPLICATION_DIRECTORY.joinpath("configuration")
MIDDLEWARE_DIRECTORY = APPLICATION_DIRECTORY.joinpath("middleware")
SWAGGER_DIRECTORY = APPLICATION_DIRECTORY.joinpath("swagger")
VIEWS_DIRECTORY = APPLICATION_DIRECTORY.joinpath("views")


logging.basicConfig()
logger = logging.getLogger("sanic-application")
logger.setLevel(logging.DEBUG)


def build_application(configuration: Dict = None) -> Sanic:
    """
    Generates and returns an instance of the sanic.app.Sanic application
    for the web server

    ***BEGIN IMPORTANT***
    This must be kept separate from the AnnotatorCLI class methods. If you attempt
    to leverage this as a class method, when the worker manager attempts to spawn
    a process to call the partially initialized factory method, it will attempt
    to pickle the instances of the class itself. So unless we take the effort
    to make the class instance pickleable, we keep this target here for the moment
    ***END IMPORTANT***

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

    static_content = build_static_content()
    for content_name, content in static_content.items():
        try:
            application.static(content["endpoint"], content["path"], name=content_name)
        except Exception as gen_exc:
            logger.exception(gen_exc)
            logger.error("Unable to add static content %s", content)
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


def build_static_content() -> Dict:
    """
    Loads the static file content

    At the moment, this is only used for the swagger openapi frontend
    we're loading
    """
    static_content = {}

    # Attempt to load the docker file path if we're running in a container.
    DOCKER_SWAGGER_PATH = pathlib.Path("/web-app/dist/index.html")

    if DOCKER_SWAGGER_PATH.exists():
        static_content["swagger"] = {"endpoint": "/", "path": DOCKER_SWAGGER_PATH}
    return static_content
