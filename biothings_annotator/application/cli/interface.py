"""
Inherited implementation of the SanicCLI from sanic.cli.app

This should allow us to support the same command line interface as the sanic
application combined with our custom override via a default configuration file
"""

from argparse import Namespace
from textwrap import indent
import copy
import functools
import json
import logging
import shutil
import sys

from sanic import Sanic
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
        self.server_configuration = None

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

        We've added additional modifications by hard-setting the values
        for the target to ensure that we always use our factory function
        for generating the application instance. We also load the
        additional server configuration here
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

        # Blanket the default args for the following:
        # > target
        # > factory
        # > simple
        self.args.target = ""
        self.args.factory = False
        self.args.simple = False

        # Load the server configuration
        server_configuration = getattr(self.args, "configuration", None)
        self.server_configuration = load_configuration(server_configuration)
        logger.info(
            "global annotator file server default configuration:\n %s", json.dumps(self.server_configuration, indent=4)
        )

    def run(self):
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

        self._precheck()
        try:
            application_loader = AppLoader(
                module_input=self.args.target,
                as_factory=self.args.factory,
                as_simple=self.args.simple,
                args=self.args,
                factory=functools.partial(build_application, self.server_configuration),
            )
            application = application_loader.load()
            logger.debug("generated biothings-annotator application from loader: %s", application)
            runtime_parameters = self.build_runtime_parameters()
        except ValueError as exc:
            logger.exception("Failed to run app: %s", exc)
        else:
            if self.args.repl:
                self._repl(application)
            for http_version in self.args.http:
                application.prepare(**runtime_parameters, version=http_version)
            if self.args.single:
                serve = Sanic.serve_single
            else:
                serve = functools.partial(Sanic.serve, app_loader=application_loader)
            logger.info(ANNOTATOR_DISPLAY)
            serve(application)

    def build_runtime_parameters(self):
        """
        Builds the runtime parameters to be passed in the `prepare` method
        for the application instance.

        Because we have the default configuration file along with the potential
        for command line arguments from the user we have to handle this specifically.

        I view three levels to this configuration:
        1) The default configuration values provided by sanic. The runtime parameters
        themselves can be found in the sanic.cli.arguments
        2) The default configuration values we store on disk specifying the service /
        biothings-annotator web server configuration defaults
        3) The command-line arguments specified when running the service at command-line

        The service itself is particular and already picks the defaults it wants for the
        web server so we automically override option 1) by default. This only leaves prioritizing
        option 2) and option 3). In this case we choose to always prioritize the command-line
        argument over the file configuration option

        So in this case we store the default parameters in the mapping below. We then load
        the runtime parameters and the file parameters

        We convert these mappings to sets of tuples to represent the unique values for each and then
        take the difference between the runtime and default parameters along with the file and
        default parameters. The difference between runtime and default are explicitly state
        parameters at the command by user or automation. The difference between file and default
        are the overridden values we specify in the file. We then do two masking operations. We
        update a copy of the default parameters with the difference between the file and default
        parameters. This way we apply all parameters from our default file to override
        the web server defaults to what we want from the web server. We then apply a second mask
        and update the parameters with the difference between the runtime and default to take any
        user or automation command-line parameters to take priority over what we specify in the file
        """
        default_parameters = {
            "access_log": None,
            "auto_tls": False,
            "coffee": False,
            "debug": False,
            "fast": False,
            "host": None,
            "motd": True,
            "noisy_exceptions": None,
            "port": None,
            "single_process": False,
            "ssl": None,
            "unix": "",
            "verbosity": 0,
            "workers": 1,
        }
        runtime_parameters = super()._build_run_kwargs()
        file_parameters = self.server_configuration["application"]["runtime"]

        default_set = set(default_parameters.items())
        runtime_set = set(runtime_parameters.items())
        file_set = set(file_parameters.items())

        # These are parameters specified explicitly at the command-line
        modified_parameters = runtime_set.difference(default_set)
        modified_mapping = {tup[0]: tup[1] for tup in modified_parameters}

        # These are parameters specified by default in the configuration file
        override_parameters = file_set.difference(default_set)
        override_mapping = {tup[0]: tup[1] for tup in override_parameters}

        explicit_parameters = copy.deepcopy(default_parameters)
        explicit_parameters.update(override_mapping)
        explicit_parameters.update(modified_mapping)
        logger.info("Runtime Parameters:\n %s", json.dumps(explicit_parameters, indent=4))
        return explicit_parameters
