"""
Pointer to the various fixture locations all stored
under the fixtures directory

> application
fixtures related to sanic application instance

> datastore
fixtures for handling and storing test data for both
input and output storage
"""

pytest_plugins = [
    "fixtures.application",
    "fixtures.datastore",
]
