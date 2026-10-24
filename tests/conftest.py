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
from unittest.mock import AsyncMock

import pytest

from biothings_annotator.annotator.settings import SERVICE_PROVIDER_API_HOST
from biothings_annotator.application import status_metadata

pytest_plugins = [
    "fixtures.application",
    "fixtures.datastore",
]

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def offline_status_metadata(request, monkeypatch):
    # Every worker now warms status metadata at startup, including when a unit
    # test exercises an unrelated endpoint. Tests can override this collector.
    if request.node.get_closest_marker("unit") is not None:
        monkeypatch.setattr(
            status_metadata,
            "collect_backend_metadata",
            AsyncMock(return_value={"biothings": {"sources": {}}, "elasticsearch": {"sources": {}}}),
        )


# ENVIRONMENT CONFIGURATION
@pytest.fixture(scope="session", autouse=True)
def annotator_environment():
    api_host = os.environ.setdefault("SERVICE_PROVIDER_API_HOST", SERVICE_PROVIDER_API_HOST)
    logger.info("Set SERVICE PROVIDER API HOST: %s for tests", api_host)
