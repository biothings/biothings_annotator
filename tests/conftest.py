"""
Pointer to the various fixture locations all stored
under the fixtures directory

> application
fixtures related to sanic application instance

> datastore
fixtures for handling and storing test data for both
input and output storage
"""

import logging
import os

import pytest

pytest_plugins = [
    "fixtures.application",
    "fixtures.datastore",
]

logger = logging.getLogger(__name__)


# ENVIRONMENT CONFIGURATION
@pytest.fixture(scope="session", autouse=True)
def annotator_environment():
    api_host = "https://biothings.test.transltr.io"
    os.environ["SERVICE_PROVIDER_API_HOST"] = api_host
    logger.info("Set SERVICE PROVIDER API HOST: %s for tests", api_host)
