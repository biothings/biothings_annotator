#!/usr/bin/env python3
import concurrent.futures
import json
import operator
import re
import time
import urllib.parse
import urllib.request


SWAGGER_UI_REPO = "https://api.github.com/repos/swagger-api/swagger-ui/releases"


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


def build_release_pagination_mapping() -> list:
    """Leverages the github API to get all release pages"""

    def make_request(url: str) -> list:
        request_instance = urllib.request.Request(url=page_url, method="GET")
        with urllib.request.urlopen(request_instance) as req_handle:
            response = json.loads(req_handle.read())
            release_mapping = [
                {
                    "version_tag": urllib.parse.urlsplit(release_entry["tarball_url"]).path.split("/")[-1],
                    "tarball": release_entry["tarball_url"],
                    "publish_timestamp": release_entry["published_at"],
                }
                for release_entry in response
            ]
            return release_mapping

    link_page_data = extract_link_page_data()

    futures = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for page_number in range(1, link_page_data["last"] + 1):
            page_url = f"{SWAGGER_UI_REPO}?page={page_number}"
            futures.append(executor.submit(make_request, page_url))
            time.sleep(1)

    full_release_collection = []
    for future in concurrent.futures.as_completed(futures):
        full_release_collection.extend(future.result())

    full_release_collection = sorted(full_release_collection, key=operator.itemgetter("publish_timestamp"))


def main():
    releases = build_release_pagination_mapping()


if __name__ == "__main__":
    main()
