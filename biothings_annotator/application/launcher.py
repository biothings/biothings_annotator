"""
`Sanic Web Application <https://sanic.dev/en/>`
+---------------+-----------+------------------------------+
| Web Framework | Interface | Handlers                     |
+===============+===========+==============================+
| sanic         | sanic     | biothings_annotator.handlers |
+---------------+-----------+------------------------------+

Parallel implementation to our defacto implementation of tornado
"""

from pathlib import Path
from typing import Union, Optional
import functools
import json
import logging
import argparse

from sanic import Sanic
from sanic.worker.loader import AppLoader

from biothings_annotator.application.views import build_routes


logging.basicConfig()
logger = logging.getLogger("sanic-application")
logger.setLevel(logging.DEBUG)


def load_configuration(configuration_file: Optional[Union[str, Path]] = None) -> dict:
    """
    Loads the global configuration for the sanic application
    configuration has been created. Otherwise we attempt to load the default
    configuration file dictated by the expected structure below:

    Expected File Structure:
    ├── configuration
    │   └── sanic.json
    └── sanic_application.py


    Example Configuration Structure:
    {
        "network": {
            "host": "0.0.0.0",
            "port": 7382
        },
        "application": {
            "settings": {
            }
        }
    }
    > network: Contains any information related to actually hosting the web
    server on the specified network
    > application: the "settings" dictionary mapping passed to the
    sanic.app.Sanic instance for configuration at runtime
    """
    if configuration_file:
        configuration_file = Path(configuration_file).resolve().absolute()
    else:
        application_file = Path(__file__).resolve().absolute()
        application_directory = Path(application_file).parent
        configuration_directory = Path(application_directory).joinpath("configuration")

        configuration_filename = "default.json"
        configuration_file = configuration_directory.joinpath(configuration_filename)

    try:
        with open(str(configuration_file), "r", encoding="utf-8") as file_handle:
            sanic_configuration = json.load(file_handle)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc

    return sanic_configuration


def get_application(configuration: dict = None) -> Sanic:
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
    delta        error_handler: Optional[ErrorHandler] = None,
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
    """
    application_configuration = configuration["application"]["configuration"]
    extension_configuration = configuration["application"]["extension"]
    configuration_settings = {**application_configuration, **extension_configuration}

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
    return application


def launch(server_configuration: Union[str, Path] = None):
    """
    Interface for starting the sanic server instance leveraging the
    biothings_annotator handlers

    Control Flow:
    > Load the configuration
    > Create a dynamic loader for creating our application across
    all worker instances:
    https://sanic.dev/en/guide/running/app-loader.html#dynamic-applications
    > Generate a sanic application from the previously built loader
    > Build an HTTP server using the network parameters from the configuration
    and the sanic application

    """
    sanic_configuration = load_configuration(server_configuration)
    logger.info("global sanic configuration:\n %s", json.dumps(sanic_configuration, indent=4))

    sanic_loader = AppLoader(factory=functools.partial(get_application, sanic_configuration))
    sanic_application = sanic_loader.load()
    logger.info("generated sanic application from loader: %s", sanic_application)

    try:
        runtime_parameters = sanic_configuration["application"]["runtime"]
        sanic_application.prepare(**runtime_parameters)
        Sanic.serve(primary=sanic_application, app_loader=sanic_loader)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc


def parse_command_line_arguments() -> argparse.Namespace:
    parser_obj = argparse.ArgumentParser()
    parser_obj.add_argument(
        "-c",
        "--conf",
        dest="configuration",
        type=str,
        required=False,
        help="Input file path for web server configuration ",
    )
    args = parser_obj.parse_args()
    return args


def main():
    """
    The entry point for launching the sanic server instance from CLI
    """
    arguments = parse_command_line_arguments()
    launch(arguments.configuration)
