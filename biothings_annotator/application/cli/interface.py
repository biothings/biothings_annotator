"""
Inherited implementation of the SanicCLI from sanic.cli.app

This should allow us to support the same command line interface as the sanic
application combined with our custom override via a default configuration file
"""

from argparse import Namespace
from textwrap import indent
import functools
import json
import logging
import shutil
import sys

import sanic
from sanic.cli.app import SanicCLI
from sanic.cli.arguments import Group
from sanic.cli.base import SanicArgumentParser, SanicHelpFormatter
from sanic.worker.loader import AppLoader

from biothings_annotator.application.cli.arguments import build_annotator_argument_groups, load_configuration
from biothings_annotator.application.cli.target import build_application

logging.basicConfig()
logger = logging.getLogger("sanic-application")
logger.setLevel(logging.DEBUG)


ANNOTATOR_DISPLAY = """

\033[38;2;255;13;104m     ▄█▄       \033[0m  ██       █  ██       █   ▄██ ████▄   █ █████ █      ▄█▄      █ █████ █   ▄██ ████▄   ███ ████
\033[38;2;255;13;104m    █   █      \033[0m  █ ██     █  █ ██     █  ██       ██      █         █   █         █      ██       ██  ██      █
\033[38;2;255;13;104m   ▀     █     \033[0m      ██   ▄      ██   ▄  ██       ██      █        ▀     █        █      ██       ██  ███ ████
\033[38;2;255;13;104m  █████████    \033[0m  █     ██ █  █     ██ █  ▄▄       ▄▄      █       █████████       █      ▄▄       ▄▄  █    ██
\033[38;2;255;13;104m █         █   \033[0m  █       ██  █       ██   ▀██ ████▀       █      █         █      █       ▀██ ████▀   █      ██

"""  # noqa


class AnnotatorCLI(SanicCLI):
    """
    Custom command line interface for the biothings annotator
    package. We wish to maintain the same interface that sanic
    supports for the command line along with adding support for a
    custom configuration file holding the annotator package defaults
    """

    DESCRIPTION = indent(
        f"""
        {ANNOTATOR_DISPLAY}

        To start running an annotator application, simply invoke the package
        name with your python instance

        >>> python3 -m biothings_annotator

        """,
        prefix=" ",
    )

    def __init__(self):
        super().__init__()
        width = shutil.get_terminal_size().columns
        self.parser = SanicArgumentParser(
            prog="biothings-annotator",
            description=self.DESCRIPTION,
            formatter_class=lambda prog: SanicHelpFormatter(
                prog,
                max_help_position=36 if width > 96 else 24,
                indent_increment=4,
                width=None,
            ),
        )

    def attach(self) -> None:
        """
        Overrided attach method which handles the argument group
        generation

        We specifically override this to hard-code the value
        for the `target` argument to always point to the application
        factory method we use internally to the biothings-annotator
        package.

        The user should never need to know or care about the
        target argument
        """
        annotator_groups = build_annotator_argument_groups()

        for annotator_group in annotator_groups:
            if annotator_group not in Group._registry:
                Group._registry.append(annotator_group)

        group_lookup = {group.name: group for group in Group._registry}

        # The general group has a group name of None
        general_group = group_lookup[None]
        Group._registry.remove(general_group)

        super().attach()

    def parse(self, additional_args: Namespace = None) -> None:
        """
        Class method for handling the argument parsing for
        the command line interface

        Originally this code was in the sanic.cli.app::run method
        but I want to split the parsing into a separate instance
        before running the web server instance
        """

        legacy_version = False
        if not additional_args:
            # This is to provide backwards compat -v to display version
            legacy_version = len(sys.argv) == 2 and sys.argv[-1] == "-v"
            additional_args = ["--version"] if legacy_version else None
        elif additional_args == ["-v"]:
            additional_args = ["--version"]

        if not legacy_version:
            parsed, unknown = self.parser.parse_known_args(args=additional_args)
            if unknown and parsed.factory:
                for arg in unknown:
                    if arg.startswith("--"):
                        self.parser.add_argument(arg.split("=")[0])

        parsed_args = self.parser.parse_args(args=additional_args)
        self.args = parsed_args

    def run(self):
        if self.inspecting:
            self._inspector()
            return

        self._precheck()
        app_loader = AppLoader(self.args.target, self.args.factory, self.args.simple, self.args)

        try:
            app = self._get_app(app_loader)
            kwargs = self._build_run_kwargs()
        except ValueError as exc:
            logger.exception(f"Failed to run app: %s", exc)
        else:
            if self.args.repl:
                self._repl(app)
            for http_version in self.args.http:
                app.prepare(**kwargs, version=http_version)
            if self.args.single:
                serve = sanic.Sanic.serve_single
            else:
                serve = functools.partial(sanic.Sanic.serve, app_loader=app_loader)
            serve(app)


def launch(configuration_arguments: dict):
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
    server_configuration = configuration_arguments.get("configuration", None)
    sanic_configuration = load_configuration(server_configuration)
    logger.info("global sanic configuration:\n %s", json.dumps(sanic_configuration, indent=4))

    sanic_loader = AppLoader(factory=functools.partial(build_application, sanic_configuration))
    sanic_application = sanic_loader.load()
    logger.info("generated sanic application from loader: %s", sanic_application)

    override_ipv4_address = configuration_arguments.get("address", None)
    override_ipv4_port = configuration_arguments.get("port", None)

    if override_ipv4_address is not None and override_ipv4_port is not None:
        sanic_configuration["application"]["runtime"]["host"] = override_ipv4_address
        sanic_configuration["application"]["runtime"]["port"] = int(override_ipv4_port)

    try:
        runtime_parameters = sanic_configuration["application"]["runtime"]
        sanic_application.prepare(**runtime_parameters)
        sanic.Sanic.serve(primary=sanic_application, app_loader=sanic_loader)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc
