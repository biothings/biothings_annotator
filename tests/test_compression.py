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
    endpoint_path = f"/{curie_id}?include_extra=0"
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

    compressed_body = compressed_response.json
    compressed_body[curie_id][0].pop("_score")

    uncompressed_body = uncompressed_response.json
    uncompressed_body[curie_id][0].pop("_score")
    assert compressed_body == uncompressed_body

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
    url = "/?include_extra=0"
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
    # {'values_changed': {"root['NCBIGene:284217']['attributes'][0]['value'][0]['_score']": {'new_value': 26.179539, 'old_value': 26.179554}}}

    compressed_body = compressed_response.json
    uncompressed_body = uncompressed_response.json

    compressed_keys = set(compressed_body.keys())
    uncompressed_keys = set(uncompressed_body.keys())
    assert compressed_keys == uncompressed_keys

    for compressed_attributes, uncompressed_attributes in zip(compressed_body.values(), uncompressed_body.values()):
        for compressed_attributes, uncompressed_attributes in zip(
            compressed_attributes.values(), uncompressed_attributes.values()
        ):
            for compressed_attribute, uncompressed_attribute in zip(compressed_attributes, uncompressed_attributes):
                compressed_values = compressed_attribute["value"]
                uncompressed_values = uncompressed_attribute["value"]
                for compressed_value, uncompressed_value in zip(compressed_values, uncompressed_values):
                    compressed_value.pop("_score", None)
                    uncompressed_value.pop("_score", None)

    assert compressed_body == uncompressed_body

    assert compressed_response.num_bytes_downloaded < uncompressed_response.num_bytes_downloaded
