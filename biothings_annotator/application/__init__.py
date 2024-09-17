import pathlib

APPLICATION_DIRECTORY = pathlib.Path(__file__).resolve().absolute().parent
CLI_DIRECTORY = APPLICATION_DIRECTORY.joinpath("cli")
CONFIGURATION_DIRECTORY = APPLICATION_DIRECTORY.joinpath("configuration")
MIDDLEWARE_DIRECTORY = APPLICATION_DIRECTORY.joinpath("middleware")
VIEWS_DIRECTORY = APPLICATION_DIRECTORY.joinpath("views")
