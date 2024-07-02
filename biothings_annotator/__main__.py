"""
Main entrypoint to launching the biothings_annotator web service
"""

from biothings_annotator.application import launcher


def main():
    launcher.launch()


if __name__ == "__main__":
    main()
