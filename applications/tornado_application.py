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

from tornado.options import options
import tornado.httpserver
import tornado.ioloop
import tornado.log
import tornado.web

from biothings import __version__
from biothings.web.handlers import BaseAPIHandler, BaseQueryHandler
from biothings.web.services.namespace import BiothingsNamespace
from biothings.web.settings import configs


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


def use_curl():
    """
    Use curl implementation for tornado http clients.
    More on https://www.tornadoweb.org/en/stable/httpclient.html
    """
    tornado.httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")


def get_handlers(biothings, addons=None):
    """
    Generates the tornado.web.Application `(regex, handler_class, options) tuples
    <http://www.tornadoweb.org/en/stable/web.html#application-configuration>`_.

    Configuration Parameters:
    > metadata
    > APP_LIST
    > APP_PREFIX
    > APP_VERSION
    """
    handlers = {}
    addons = addons or []
    for rule in biothings.config.APP_LIST + addons:
        pattern = rule[0]
        handler = load_class(rule[1])
        setting = rule[2] if len(rule) == 3 else {}
        assert handler, rule[1]

        if "{typ}" in pattern or "{tps}" in pattern:
            if not issubclass(handler, BaseQueryHandler):
                raise TypeError("Not a biothing_type-aware handler.")
            if "{tps}" in pattern and len(biothings.metadata.types) <= 1:
                continue  # '{tps}' routes only valid for multi-type apps
            for biothing_type in biothings.metadata.types:
                _pattern = pattern.format(
                    pre=biothings.config.APP_PREFIX,
                    ver=biothings.config.APP_VERSION,
                    typ=biothing_type,
                    tps=biothing_type,
                ).replace("//", "/")
                _setting = dict(setting)
                _setting["biothing_type"] = biothing_type
                handlers[_pattern] = (_pattern, handler, _setting)
        elif "{pre}" in pattern or "{ver}" in pattern:
            pattern = pattern.format(pre=biothings.config.APP_PREFIX, ver=biothings.config.APP_VERSION).replace(
                "//", "/"
            )
            if "()" not in pattern:
                handlers[pattern] = (pattern, handler, setting)
        else:  # no pattern translation
            handlers[pattern] = (pattern, handler, setting)

    handlers = list(handlers.values())
    logger.info("API Handlers:\n%s", pformat(handlers, width=200))
    return handlers


def get_app(cls, config, settings=None, handlers=None):
    """
    Return the tornado.web.Application defined by this config.
    **Additional** settings and handlers are accepted as parameters.
    """
    if isinstance(config, configs.ConfigModule):
        biothings = BiothingsNamespace(config)
        _handlers = BiothingsAPI._get_handlers(biothings, handlers)
        _settings = BiothingsAPI._get_settings(biothings, settings)
        app = cls(_handlers, **_settings)
        app.biothings = biothings
        app._populate_optionsets(config, _handlers)
        app._populate_handlers(_handlers)
        return app
    if isinstance(config, configs.ConfigPackage):
        biothings = BiothingsNamespace(config.root)
        _handlers = [(f"/{c.APP_PREFIX}/.*", cls.get_app(c, settings)) for c in config.modules]
        _settings = BiothingsAPI._get_settings(biothings, settings)
        app = cls(_handlers + handlers or [], **_settings)
        app.biothings = biothings
        # app._populate_optionsets(config, handlers or [])
        # app._populate_handlers(handlers or [])
        app._populate_optionsets(config, _handlers + handlers or [])
        app._populate_handlers(_handlers + handlers or [])
        return app
    raise TypeError("Invalid config type. Must be a ConfigModule or ConfigPackage.")


class TornadoAPILauncher:
    # tornado uses its own event loop which is
    # a wrapper around the asyncio event loop

    def __init__(self, config=None):
        # About debug mode in tornado:
        # https://www.tornadoweb.org/en/stable/guide/running.html \
        # #debug-mode-and-automatic-reloading
        super().__init__(config)
        self.handlers = []  # additional handlers
        self.host = None

    @staticmethod
    def use_curl():
        """ """
        tornado.httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")

    def get_app(self):
        return BiothingsAPI.get_app(self.config, self.settings, self.handlers)

    def get_server(self):
        # Use case example:
        # Run API in an external event loop.
        app = self.get_app()
        logger.info("All Handlers:\n%s", pformat(app.biothings.handlers, width=200))
        return tornado.httpserver.HTTPServer(app, xheaders=True)

    def start(self, port=8000):
        self._configure_logging()

        http_server = self.get_server()
        http_server.listen(port, self.host)

        logger.info('Server is running on "%s:%s"...', self.host or "0.0.0.0", port)
        loop = tornado.ioloop.IOLoop.instance()
        loop.start()


def load_configuration(configuration_file: Optional[Union[str, Path]] = None) -> dict:
    """
    Loads the global configuration for the tornado application

    Optional argument to load the provided configuration_file if a custom
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
    tornado.web.Application instance for configuration at runtime
    """
    if configuration_file:
        configuration_file = Path(configuration_file).resolve().absolute()
    else:
        application_file = Path(__file__).resolve().absolute()
        application_directory = Path(application_file).parent

        configuration_filename = "tornado.json"
        configuration_file = application_directory.joinpath(configuration_filename)

    try:
        with open(str(configuration_file), "r", encoding="utf-8") as file_handle:
            tornado_configuration = json.load(file_handle)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc

    return tornado_configuration


def get_application(configuration: dict) -> tornado.web.Application:
    """
    Takes the loaded configuration and generates an instance of
    ServerApplication, which inherits from tornado.web.Application
    """


def main(app_handlers=None, app_settings=None, use_curl=False):
    """
    Start a Biothings API Server
    """
    app_handlers = app_handlers or []
    app_settings = app_settings or {}

    launcher = TornadoAPILauncher(options.conf)

    try:
        if app_settings:
            launcher.settings.update(app_settings)
        if app_handlers:
            launcher.handlers = app_handlers
        if use_curl:
            launcher.use_curl()

        launcher.host = options.address
        launcher.settings.update(debug=options.debug)
        launcher.settings.update(autoreload=options.autoreload)
    except Exception:
        pass

    tornado_configuration = load_configuration()
    logger.info("global tornado configuration:\n %s", json.dumps(tornado_configuration, indent=4))
    tornado_application = get_application(tornado_configuration)

    app = BiothingsAPI.get_app(self.config, self.settings, self.handlers)
    logger.info("All Handlers:\n%s", pformat(app.biothings.handlers, width=200))
    http_server = tornado.httpserver.HTTPServer(app, xheaders=True)
    port = 8000
    host = "0.0.0.0"
    http_server.listen(port, self.host)

    logger.info('Server is running on "%s:%s"...', self.host or "0.0.0.0", port)
    loop = tornado.ioloop.IOLoop.instance()
    loop.start()


if __name__ == "__main__":
    main()
