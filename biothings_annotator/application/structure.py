import pathlib
import importlib.resources


MODULE_NAME = "biothings_annotator"
ROOT_DIRECTORY = importlib.resources.files(MODULE_NAME)

# Package directories
ANNOTATOR_DIRECTORY = ROOT_DIRECTORY.joinpath("annotator")
APPLICATION_DIRECTORY = ROOT_DIRECTORY.joinpath("application")
WEB_APP_DIRECTORY = ROOT_DIRECTORY.joinpath("webapp")

# Inner application directories
CLI_DIRECTORY = APPLICATION_DIRECTORY.joinpath("cli")
CONFIGURATION_DIRECTORY = APPLICATION_DIRECTORY.joinpath("configuration")
EXCEPTIONS_DIRECTORY = APPLICATION_DIRECTORY.joinpath("exceptions")
MIDDLEWARE_DIRECTORY = APPLICATION_DIRECTORY.joinpath("middleware")
VIEWS_DIRECTORY = APPLICATION_DIRECTORY.joinpath("views")

# Docker directories
DOCKER_WEB_APP_DIRECTORY = pathlib.Path("/webapp")
