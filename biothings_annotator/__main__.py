"""
Main entrypoint to launching the biothings_annotator web service
"""

import argparse
import logging

from application import sanic, tornado


logger = logging.getLogger(__name__)


def launch_service(arguments: argparse.Namespace):
    """
    Launcher for the different web servers supported
    by the biothings_annotator web service
    """
    if arguments.sanic:
        sanic.launch()
    elif arguments.tornado:
        tornado.launch()


def parse_arguments() -> argparse.Namespace:
    """
    Handles parsing command line arguments
    """
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-s",
        "--sanic",
        dest="sanic",
        action=argparse.BooleanOptionalAction,
        help="flag for running the sanic web server",
    )
    group.add_argument(
        "-t",
        "--tornado",
        dest="tornado",
        action=argparse.BooleanOptionalAction,
        help="flag for running the tornado web server",
    )
    args = parser.parse_args()
    return args


def main():
    arguments = parse_arguments()
    launch_service(arguments)


if __name__ == "__main__":
    main()
