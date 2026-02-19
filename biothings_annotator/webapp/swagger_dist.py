#!/usr/bin/env python3
import argparse
import datetime
import json
import logging
import operator
import pathlib
import re
import sqlite3
import tarfile
import time
import urllib.parse
import urllib.request


SWAGGER_UI_REPO = "https://api.github.com/repos/swagger-api/swagger-ui/releases"
SWAGGER_UI_DIRECTORY = pathlib.Path(__file__).parent.joinpath("swaggerui")

logger = logging.getLogger("swagger-distribution")
logging.basicConfig()
logger.setLevel(logging.DEBUG)


def extract_link_page_data() -> dict:
    """Extracts the link page references from github api link header"""
    request_instance = urllib.request.Request(url=SWAGGER_UI_REPO, method="HEAD")
    with urllib.request.urlopen(request_instance) as req_handle:
        link_header = req_handle.getheader("link")

        # (?<=page=) | positive lookbehind
        # >>> assert that the regex matches <page=> literally (case sensitive)
        # [^>] | match a single character not present in the list below
        # * matches the previous token between zero and unlimited times, as many times as possible, giving back as needed (greedy)
        # > matches the character > with index 6210 (3E16 or 768) literally (case sensitive)
        page_count_search_expr = re.compile(r"(?<=page=)[^>]*")

        # (?<=rel=\") | positive lookbehind
        # >>> assert that the regex matches <rel=> iterally (case sensitive)
        # >>> \" matches the character " with index 3410 (2216 or 428) literally (case sensitive)
        # match a single character not present in the list below [^\"]
        # * matches the previous token between zero and unlimited times, as many times as possible, giving back as needed (greedy)
        # \" matches the character " with index 3410 (2216 or 428) literally (case sensitive)
        page_attribute_search_expr = re.compile(r"(?<=rel=\")[^\"]*")

        link_page_data = {}
        for link_page_entry in link_header.split(","):
            page_count = int(re.search(page_count_search_expr, link_page_entry).group())
            page_attribute = str(re.search(page_attribute_search_expr, link_page_entry).group())
            link_page_data[page_attribute] = page_count
    return link_page_data


def generate_local_cache(connection: sqlite3.Connection) -> None:
    """Creates our cache database for release links.

    There's fairly strict rate limits in place for non-authenticated
    users using this github API (fairly reasonable). We need to ensure we don't
    hammer it by caching our results after one run of the script, especially
    given the release schedule isn't frequently updating
    """
    cursor = connection.cursor()
    release_table = (
        "CREATE TABLE IF NOT EXISTS releases("
        "version_tag TEXT PRIMARY KEY NOT NULL, "
        "tarball TEXT, "
        "publish_timestamp TEXT, "
        "insert_timestamp TEXT"
        ");"
    )
    cursor.execute(release_table)
    connection.commit()


def update_release_cache(connection: sqlite3.Connection, release_metadata: list[dict]) -> None:
    """Update our cache with all links from the releases."""
    cursor = connection.cursor()
    cursor.executemany(
        "INSERT INTO releases VALUES(:version_tag, :tarball, :publish_timestamp, :insert_timestamp)", release_metadata
    )
    connection.commit()


def lookup_cached_releases(connection: sqlite3.Connection) -> list:
    """Looks up the cached releases for usage if they aren't stale."""
    cursor = connection.cursor()
    stale_cache_check_query = "SELECT * FROM releases WHERE insert_timestamp >= DATE('now', '-7 days');"
    results = cursor.execute(stale_cache_check_query).fetchall()
    return results


def extract_releases(connection: sqlite3.Connection) -> list:
    """Leverages the github API to get all release pages"""

    def make_request(page_url: str) -> list:
        request_instance = urllib.request.Request(url=page_url, method="GET")
        with urllib.request.urlopen(request_instance) as req_handle:
            response = json.loads(req_handle.read())
            release_mapping = [
                {
                    "version_tag": urllib.parse.urlsplit(release_entry["tarball_url"]).path.split("/")[-1],
                    "tarball": release_entry["tarball_url"],
                    "publish_timestamp": release_entry["published_at"],
                    "insert_timestamp": datetime.datetime.now().isoformat(),
                }
                for release_entry in response
            ]
            return release_mapping

    logger.info("Loading cached relases")
    releases = lookup_cached_releases(connection)

    if len(releases) == 0:
        logger.info("Updating stale cache")
        link_page_data = extract_link_page_data()

        releases = []
        for page_number in range(1, link_page_data["last"] + 1):
            page_url = f"{SWAGGER_UI_REPO}?page={page_number}"
            logger.info("processing pagination url: %s", page_url)
            releases.extend(make_request(page_url))
            time.sleep(5)

        update_release_cache(connection, releases)
        releases = sorted(releases, key=operator.itemgetter("publish_timestamp"), reverse=True)
    return releases


def display_releases(connection: sqlite3.Connection):
    """Displays the swagger-ui releases in a tabular format."""
    releases = extract_releases(connection)

    version_padding = max(len(release["version_tag"]) for release in releases)
    url_padding = max(len(release["tarball"]) for release in releases)
    timestamp_padding = max(len(release["publish_timestamp"]) for release in releases)

    row_header = f"|{'version':^{version_padding}}|{'url':^{url_padding}}|{'timestamp':^{timestamp_padding}}|"
    print(row_header)
    print("-" * len(row_header))
    for release in releases:
        print(
            f"|{release['version_tag']:^{version_padding}}|{release['tarball']:^{url_padding}}|{release['publish_timestamp']:^{timestamp_padding}}|"
        )


def update_release(connection: sqlite3.Connection, release_version: str):
    """Updates the swagger-ui local files based off provided release."""
    releases = extract_releases(connection)

    target_release = {release["version_tag"]: release for release in releases}.get(release_version, None)
    if target_release is None:
        logger.warning("Unable to find version %s. Please select one of the releases from the table below")
        display_releases(connection)
    elif target_release is not None:
        tarball_url = target_release["tarball"]
        request_instance = urllib.request.Request(url=tarball_url, method="GET")
        with urllib.request.urlopen(request_instance) as req_handle:
            with tarfile.open(fileobj=req_handle, mode="r|gz") as tar_handle:
                member: tarfile.TarInfo
                for member in tar_handle:
                    try:
                        if pathlib.Path(member.path).parts[1] == "dist":
                            subpath = "/".join(SWAGGER_UI_DIRECTORY.parts[0:-1])[1:]
                            new_path = SWAGGER_UI_DIRECTORY.relative_to(subpath)
                            member.path = str(new_path.joinpath(pathlib.Path(member.path).parts[-1]))
                            if member.isfile():
                                tar_handle.extract(member=member, filter="data")
                    except IndexError:
                        pass

        logger.info("Successfully unpacked swagger distribution version %s", release_version)
        with open(SWAGGER_UI_DIRECTORY.joinpath("UI_VERSION"), "w", encoding="utf-8") as handle:
            handle.write(release_version)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="swagger-ui")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-d",
        "--display",
        dest="display",
        action="store_true",
        help="display the release versions for the swagger-ui files",
    )
    group.add_argument(
        "-u",
        "--update",
        type=str,
        dest="swagger_version",
        help="update the local swagger-ui distribution to specified version",
    )
    arguments = parser.parse_args()
    return arguments


def main():
    args = parse_arguments()

    try:
        cache_database = pathlib.Path(__file__).parent.absolute().resolve().joinpath(".swagger_cache.sqlite3")
        connection = sqlite3.connect(cache_database)
        connection.row_factory = sqlite3.Row
        generate_local_cache(connection)
    except Exception as gen_exc:
        logger.error("Unable to generate local cache database")
        logger.exception(gen_exc)
        raise gen_exc

    try:
        if args.display:
            display_releases(connection)
        else:
            update_release(connection, args.swagger_version)
    except Exception as gen_exc:
        logger.exception(gen_exc)
        raise gen_exc
    finally:
        connection.close()


if __name__ == "__main__":
    main()
