"""
`Sanic Web Application <https://sanic.dev/en/>`
+---------------+-----------+------------------------------+
| Web Framework | Interface | Handlers                     |
+===============+===========+==============================+
| sanic         | sanic     | biothings_annotator.handlers |
+---------------+-----------+------------------------------+

Parallel implementation to our defacto implementation of tornado
"""

import sanic
import swagger_ui

from biothings_annotator.application.cli.interface import AnnotatorCLI
from biothings_annotator.application import CONFIGURATION_DIRECTORY


def main():
    """
    The entry point for launching the sanic server instance from CLI
    """
    application: sanic.Sanic = AnnotatorCLI()

    application.attach()
    application.parse()
    application.run()


def generate_openapi_swagger_ui(application: sanic.Sanic) -> None:
    openapi_file = CONFIGURATION_DIRECTORY.joinpath("openapi.json")
    swagger_ui.api_doc(application, config_path=openapi_file, url_prefix="/", title="Annotation UI")
