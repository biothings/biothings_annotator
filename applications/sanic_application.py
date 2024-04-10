"""
`Sanic Web Application <https://sanic.dev/en/>`
+---------------+-----------+------------------------------+
| Web Framework | Interface | Handlers                     |
+===============+===========+==============================+
| sanic         | sanic     | biothings_annotator.handlers |
+---------------+-----------+------------------------------+

Parallel implementation to our defacto implementation of tornado


"""

import json
from pathlib import Path
from pprint import pformat
from pydoc import locate
from types import SimpleNamespace
from typing import Union, Optional
import inspect
import logging
import os
import sys

import sanic
from sanic.app import Sanic
import biothings_annotator

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    """
    application = Sanic(name="SANIC")
    return application


application = get_application()
application.add_route(biothings_annotator.AnnotatorView.as_view(),
                      "/annotation")


def load_configuration(configuration_file: Optional[Union[str, Path]] = None) -> dict:
    """
    Loads the global configuration for the tornado application
    configuration has been created. Otherwise we attempt to load the default
    configuration file dictated by the expected structure below:

    Expected File Structure:
    ├── configuration
    │   └── tornado.json
    └── tornado.py

    Example Configuration Structure:
    {
        "network": {
            "host": "0.0.0.0",
            "port": 8475
        },
        "application": {
            "settings": {
                "autoreload": true,
                "compiled_template_cache": false,
                "compress_response": true,
                "debug": true,
                "serve_traceback": true,
                "static_hash_cache": false
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

        configuration_filename = "sanic.json"
        configuration_file = application_directory.joinpath(configuration_filename)

    try:
        with open(str(configuration_file), "r", encoding="utf-8") as file_handle:
            sanic_configuration = json.load(file_handle)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc

    return sanic_configuration


# def get_server(sanic_application: sanic.app.Sanic) -> sanic.server.AsyncioServer:


def main():
    """
    Start a Biothings API Server
    """
    # sanic_configuration = load_configuration()
    # logger.info("global sanic configuration:\n %s", json.dumps(sanic_configuration, indent=4))
    # sanic_application = get_application(sanic_configuration)
    # sanic_server = get_server(sanic_application)
    # serve(sanic_server)
    # sanic_server.server




    # app = BiothingsAPI.get_app(self.config, self.settings, self.handlers)
    # logger.info("All Handlers:\n%s", pformat(app.biothings.handlers, width=200))
    # http_server = tornado.httpserver.HTTPServer(app, xheaders=True)
    # port = 8000
    # host = "0.0.0.0"
    # http_server.listen(port, self.host)

    # logger.info('Server is running on "%s:%s"...', self.host or "0.0.0.0", port)
    # loop = tornado.ioloop.IOLoop.instance()
    # loop.start()


if __name__ == "__main__":
    main()
    application.run()
