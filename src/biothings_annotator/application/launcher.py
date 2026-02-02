"""
`Sanic Web Application <https://sanic.dev/en/>`
+---------------+-----------+------------------------------+
| Web Framework | Interface | Handlers                     |
+===============+===========+==============================+
| sanic         | sanic     | biothings_annotator.handlers |
+---------------+-----------+------------------------------+

Parallel implementation to our defacto implementation of tornado
"""

from biothings_annotator.application.cli.interface import AnnotatorCLI


def main():
    """
    The entry point for launching the sanic server instance from CLI
    """
    application = AnnotatorCLI()
    application.attach()
    application.parse()
    application.run()
