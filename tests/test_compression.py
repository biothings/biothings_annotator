import sanic


def test_get_compression(test_annotator: sanic.Sanic):
    """
    Tests the brotli compression when hitting our GET endpoint
    annotating a CURIE ID request

    At the time of writing this test (July 25th 2024), we have the following
    values:
    compressed   response size : 538  bytes
    uncompressed response size : 1218 bytes

    """
    curie_id = "NCBIGene:1017"
    endpoint_path = f"/{curie_id}"
    empty_compression_headers = {"Accept-Encoding": ""}
    uncompressed_request, uncompressed_response = test_annotator.test_client.request(
        endpoint_path, http_method="get", headers=empty_compression_headers
    )
    assert uncompressed_request.headers["Accept-Encoding"] == empty_compression_headers["Accept-Encoding"]

    compressed_headers = {"Accept-Encoding": "br, gzip, deflate"}
    compressed_request, compressed_response = test_annotator.test_client.request(
        endpoint_path, http_method="get", headers=compressed_headers
    )
    assert compressed_request.headers["Accept-Encoding"] == compressed_headers["Accept-Encoding"]
    assert compressed_response.json == uncompressed_response.json

    assert compressed_response.num_bytes_downloaded < uncompressed_response.num_bytes_downloaded


def test_post_compression(test_annotator: sanic.Sanic, trapi_request: dict):
    """
    Tests the brotli compression when hitting our POST endpoint
    annotating a TRAPI request

    At the time of writing this test (July 25th 2024), we have the following
    values:
    compressed   response size : 135222  bytes
    uncompressed response size : 3075763 bytes
    """
    url = "/"
    empty_compression_headers = {"Accept-Encoding": ""}
    uncompressed_request, uncompressed_response = test_annotator.test_client.request(
        url, http_method="post", json=trapi_request, headers=empty_compression_headers
    )
    assert uncompressed_request.headers["Accept-Encoding"] == empty_compression_headers["Accept-Encoding"]

    compressed_headers = {"Accept-Encoding": "br, gzip, deflate"}
    compressed_request, compressed_response = test_annotator.test_client.request(
        url, http_method="post", json=trapi_request, headers=compressed_headers
    )
    assert compressed_request.headers["Accept-Encoding"] == compressed_headers["Accept-Encoding"]
    assert compressed_response.json == uncompressed_response.json

    assert compressed_response.num_bytes_downloaded < uncompressed_response.num_bytes_downloaded
