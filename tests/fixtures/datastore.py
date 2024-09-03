from pathlib import Path
import logging
import shutil
import sqlite3

import pytest


logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def performance_database(request) -> sqlite3.Connection:
    """
    Performance database for storing HTTP responses
    """
    module_root_path = Path(request.config.rootpath)
    tests_directory = module_root_path.joinpath("tests")
    database_directory = tests_directory.joinpath("database")
    database_directory.mkdir(mode=511, parents=True, exist_ok=True)

    database_path = database_directory.joinpath("performance_testing.db")
    try:
        connection = sqlite3.connect(str(database_path))
    except Exception as exc:
        raise exc
    yield connection
    connection.close()


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
