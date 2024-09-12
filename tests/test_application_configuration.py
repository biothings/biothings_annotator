"""
Tests our ability to configure the application, primarily for ensuring a proper deployment
"""

import os

import pytest

from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.settings import ANNOTATOR_CLIENTS, SERVICE_PROVIDER_API_HOST
from biothings_annotator.annotator.utils import get_client


SERVICE_PROVIDER_API_HOST_CI = "https://biothings.ci.transltr.io"
SERVICE_PROVIDER_API_HOST_TEST = "https://biothings.test.transltr.io"
SERVICE_PROVIDER_API_HOST_PROD = "https://biothings.transltr.io"


@pytest.mark.unit
@pytest.mark.parametrize(
    "host", (SERVICE_PROVIDER_API_HOST_CI, SERVICE_PROVIDER_API_HOST_TEST, SERVICE_PROVIDER_API_HOST_PROD, None)
)
def test_environment_configuration(host: str):
    """
    Tests modifying the environment values for the host API
    so that we can launch the application with the following values
    for the host API:
    >>> "https://biothings.ci.transltr.io"
    >>> "https://biothings.test.transltr.io"
    >>> "https://biothings.transltr.io"

    This only requires us checking the annotator instance and ensuring it is
    able to grab the correct environment variable and then applying that to
    the biothings_client construction
    """
    try:
        if host:
            os.environ["SERVICE_PROVIDER_API_HOST"] = host

        annotator_instance = Annotator()

        if host:
            assert annotator_instance.api_host == host
        else:
            assert annotator_instance.api_host == SERVICE_PROVIDER_API_HOST

        nodes = ["phenotype", "ncit", "extra"]
        for node_type in nodes:
            client = get_client(node_type, annotator_instance.api_host)
            endpoint = ANNOTATOR_CLIENTS[node_type]["client"]["endpoint"]

            if client is None:
                assert False, f"Missing client for {annotator_instance.api_host}/{endpoint}"

            assert client.url == f"{annotator_instance.api_host}/{endpoint}"
            assert ANNOTATOR_CLIENTS[node_type]["client"]["instance"] == client
    finally:
        if os.environ.get("SERVICE_PROVIDER_API_HOST", None) is not None:
            del os.environ["SERVICE_PROVIDER_API_HOST"]

        nodes = ["phenotype", "ncit", "extra"]
        for node_type in nodes:
            ANNOTATOR_CLIENTS[node_type]["client"]["instance"] = None
