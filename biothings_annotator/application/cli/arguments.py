"""
Collection of ArgumentGroups and helper methods and
handlers for the application interface configuration
"""

from pathlib import Path
import json
import logging
from typing import List, Optional, Union

from sanic import __version__
from sanic.cli.arguments import Group
from sanic_routing import __version__ as __routing_version__

from biothings_annotator.application import CONFIGURATION_DIRECTORY

logging.basicConfig()
logger = logging.getLogger("sanic-application")
logger.setLevel(logging.DEBUG)


class VersionGroup(Group):
    """
    Because we remove the `GeneralGroup` to eliminate the target
    option, we re-add a version group to include the potential argument
    handling here
    """

    name = "Version"

    def attach(self):
        version_str = f"Sanic {__version__}; " f"Routing {__routing_version__};"
        self.container.add_argument("--version", action="version", version=version_str)


class FileConfigurationGroup(Group):
    """
    File configuration command line argument group specific
    to the biothings-annotator. Used for the file configuration we allow
    the user to load
    """

    name = "FileConfiguration"

    def attach(self):
        """
        Class method for building the command line argument groups
        and adding them to the internal registry that sanic uses
        for storing the command line arguments

        Effectively the `Group` class object is a container for grouping
        different flavors of command line arguments under different umbrellas.
        They all inherit from one `Group` parent class that has the following
        structure (as of September 16th 2024) | Sanic 24.6.0
        https://github.com/sanic-org/sanic/commit/392a4973663631d011bd147a97347fb442d5a532
        (Seems that this interface has been stable for 3 years)

        ```
        class Group:
            name: Optional[str]
            container: Union[ArgumentParser, _ArgumentGroup]
            _registry: List[Type[Group]] = []

            def __init_subclass__(cls) -> None:
                Group._registry.append(cls)
        ```

        This structure has a class-wide list called _registry that stores all
        of the Group instances internally so that all command line arguments can be accessed
        from each other

        So because we've inherited from the sanic.cli.arguments::Group object,
        this will automatically get added to the registry
        """
        self.container.add_argument(
            "-c",
            "--conf",
            dest="configuration",
            type=str,
            help="Input file path for web server configuration ",
            required=False,
        )


def build_annotator_argument_groups() -> List[Group]:
    """
    Generates a Group list for each of the custom annotator ArgumentGroups
    """
    group_list = [
        FileConfigurationGroup,
        VersionGroup,
    ]
    return group_list


def load_configuration(configuration_file: Optional[Union[str, Path]] = None) -> dict:
    """
    Loads the global configuration for the sanic application
    configuration has been created. Otherwise we attempt to load the default
    configuration file dictated by the expected structure below:

    Expected File Structure:
    ├── configuration
    │   └── default.json
    └── launcher.py


    Example Configuration Structure:
    "application": {
        "configuration": {
            ...
        },
        "extension": {
            ...
        },
        "runtime": {
            ...
        }
    }
    """
    if configuration_file:
        configuration_file = Path(configuration_file).resolve().absolute()
    else:
        configuration_filename = "default.json"
        configuration_file = CONFIGURATION_DIRECTORY.joinpath(configuration_filename)

    try:
        with open(str(configuration_file), "r", encoding="utf-8") as file_handle:
            sanic_configuration = json.load(file_handle)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc

    return sanic_configuration
