"""
`Tornado Web Application <https://www.tornadoweb.org/en/stable/index.html>`
+---------------+-----------+------------------------------+
| Web Framework | Interface | Handlers                     |
+===============+===========+==============================+
| Tornado       | Tornado   | biothings_annotator.handlers |
+---------------+-----------+------------------------------+

Stripped down version from the biothings.api launcher to provide
an interface for launching the web server

*Notes*
- tornado uses its own event loop which is a wrapper around the asyncio event loop
- About debug mode in tornado:
    > https://www.tornadoweb.org/en/stable/guide/running.html#debug-mode-and-automatic-reloading
- Use curl implementation for tornado http clients.
    > https://www.tornadoweb.org/en/stable/httpclient.html

"""

from pathlib import Path
from typing import Union, Optional
import importlib
import json
import logging

import tornado


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def load_configuration(configuration_file: Optional[Union[str, Path]] = None) -> dict:
    """
    Loads the global configuration for the tornado application

    Optional argument to load the provided configuration_file if a custom
    configuration has been created. Otherwise we attempt to load the default
    configuration file dictated by the expected structure below:

    Expected File Structure:
    ├── configuration
    │   └── tornado.json
    └── tornado_application.py

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
            },
            "handlers": [
                {
                    "regex": "/annotator(?:/([^/]+))?/?",
                    "handler": "AnnotatorHandler",
                    "package": "biothings_annotator"
                }
            ]
        }
    }

    > network: Contains any information related to actually hosting the web
    server on the specified network
    > application: the "settings" dictionary mapping passed to the
    tornado.web.Application instance for configuration at runtime
    """
    if configuration_file:
        configuration_file = Path(configuration_file).resolve().absolute()
    else:
        application_file = Path(__file__).resolve().absolute()
        application_directory = Path(application_file).parent
        configuration_directory = Path(application_directory).joinpath("configuration")

        configuration_filename = "tornado.json"
        configuration_file = configuration_directory.joinpath(configuration_filename)

    try:
        with open(str(configuration_file), "r", encoding="utf-8") as file_handle:
            tornado_configuration = json.load(file_handle)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc

    return tornado_configuration


class ServerApplication(tornado.web.Application):
    """
    https://www.tornadoweb.org/en/stable/web.html#application-configuration
    Main entrypoint for generating the tornado web server application.

    Constructor has the following signature with parameter definition
    explainations at the above link:

    class tornado.web.Application(
        handlers: Optional[List[Union[Rule, Tuple]]] = None,
        default_host: Optional[str] = None,
        transforms: Optional[List[Type[OutputTransform]]] = None,
        **settings
    )
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def get_application(configuration: dict) -> tornado.web.Application:
    """
    Takes the loaded configuration and generates an instance of
    ServerApplication, which inherits from tornado.web.Application
    """
    application_settings = configuration["application"]["settings"]
    application_handlers = configuration["application"]["handlers"]
    handlers = []
    for handler_mapping in application_handlers:
        try:
            handler_package = importlib.import_module(handler_mapping["package"])
            handler_instance = getattr(handler_package, handler_mapping["handler"])
            handler_regex = handler_mapping["regex"]
            handlers.append((handler_regex, handler_instance))
        except Exception as gen_exc:
            logger.exception(gen_exc)

    application = tornado.web.Application(handlers=handlers, **application_settings)
    return application


def main():
    """
    Interface for starting the tornado server instance leveraging the
    biothings_annotator handlers

    Control Flow:
    > Load the configuration
    > Generate a tornado application from the configuration parameters
    > Build an HTTP server using the network parameters from the configuration
    and the tornado application
    > Start the IO loop

    """
    tornado_configuration = load_configuration()
    logger.info("global tornado configuration:\n %s", json.dumps(tornado_configuration, indent=4))
    tornado_application = get_application(tornado_configuration)
    logger.info("generated tornado application: %s", tornado_application)

    try:
        http_server = tornado.httpserver.HTTPServer(tornado_application, xheaders=True)
        tornado_host = tornado_configuration["network"]["host"]
        tornado_port = tornado_configuration["network"]["port"]
        http_server.listen(port=tornado_port, address=tornado_host)
        logger.info("HTTP server listening @ %s:%s", tornado_host, tornado_port)
        loop = tornado.ioloop.IOLoop.instance()
        loop.start()
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc


if __name__ == "__main__":
    main()
