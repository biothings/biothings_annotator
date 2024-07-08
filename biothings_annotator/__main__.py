"""
Main entrypoint to launching the biothings_annotator web service
"""

import argparse

from biothings_annotator.application import launcher


def parse_command_line_arguments() -> argparse.Namespace:
    parser_obj = argparse.ArgumentParser()
    parser_obj.add_argument(
        "-c",
        "--conf",
        dest="configuration",
        type=str,
        required=False,
        help="Input file path for web server configuration ",
    )
    args = parser_obj.parse_args()
    return args


def main():
    arguments = parse_command_line_arguments()
    launcher.launch(arguments.configuration)


if __name__ == "__main__":
    main()
