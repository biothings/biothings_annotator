"""
Fixtures for testing the biothings_annotator package
"""

import json
from pathlib import Path
import logging
import shutil

import pytest


logger = logging.getLogger(__name__)


pytest_plugins = [
    "fixtures.application",
]


@pytest.fixture(scope="session")
def temporary_data_storage(tmp_path_factory, request) -> Path:
    """
    Builds a session level test structure to avoid potentially modifying
    repository test data

    > Takes the session level items discovered as tests and iterates over
      them
    > Each test item will have the following:
        > test_location
        > test_node
        > test_name
    > We search for a potential hardcoded data directory relative to the
      discovered test to add to our collection of test data directories
    > Takes these discovered directories and copies all the corresponding
      test data into a temporary location for usage during the tests
    > Fixture yields the temporary directory structure to each test that
      calls it so the test can utilize any potential data it requires
      without modifying the stored test data within the repository
    > Cleans up the temporary directory after the test session has completed
    """
    for test_function in request.session.items:
        test_location, test_node, test_name = test_function.location
        logger.info(f"Discovered {test_name}@{test_location} given node #{test_node}")

    module_root_path = request.config.rootpath
    test_data_directories = ["tests/data"]
    test_data_locations = [module_root_path / test_data_directory for test_data_directory in test_data_directories]

    temp_directory_name = "library_of_congress"
    temp_directory = tmp_path_factory.mktemp(temp_directory_name)
    for data_directory in test_data_locations:
        if data_directory.is_dir():
            shutil.copytree(
                src=str(data_directory),
                dst=str(temp_directory),
                dirs_exist_ok=True,
            )
            logger.info(f"Copied {data_directory} -> {temp_directory}")

    yield temp_directory
    shutil.rmtree(str(temp_directory))


@pytest.fixture(scope="session")
def data_store(temporary_data_storage, request):
    """
    Used for accessing data files stored on the file system used for tests
    """
    data_file_name = str(request.param)
    data_file_path = temporary_data_storage.joinpath(data_file_name)
    with open(str(data_file_path), "r", encoding="utf-8") as file_handle:
        data_content = json.load(file_handle)
        return data_content
