import pytest
import sanic
from sanic_testing import TestManager


from biothings_annotator.application.cli.target import build_application
from biothings_annotator.application.cli.arguments import load_configuration


@pytest.fixture(scope="module")
def test_annotator() -> sanic.Sanic:
    """
    Generate an application instance from the biothings_annotator
    """
    default_configuration = load_configuration()
    default_configuration["application"]["runtime"]["debug"] = False
    default_configuration["application"]["runtime"]["port"] = 7777
    application = build_application(default_configuration)
    TestManager(application)
    return application
