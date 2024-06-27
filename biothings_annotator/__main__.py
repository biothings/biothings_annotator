"""
Main entrypoint to launching the biothings_annotator web service
"""

from application import sanic


def main():
    sanic.launch()


if __name__ == "__main__":
    main()
