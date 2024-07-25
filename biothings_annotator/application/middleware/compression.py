"""
Compression middleware for implementing brotli compression for our HTTP
requests and responses

Because the scope of the annotator endpoint is fairly small, we only really
need to support JSON as all endpoints return JSON

Future compression algorithms could be added in the future, but for the moment
we will limit to brotli for simplicity
"""

import logging

import brotli
import sanic

# Configuration Parameters
COMPRESSION_THRESHOLD = 1000
MIME_TYPES = [
    "text/html",
    "application/json",
]
COMPRESSION = ["br"]

logging.basicConfig()
logger = logging.getLogger("sanic-application")
logger.setLevel(logging.DEBUG)


async def compress_response(request: sanic.request.types.Request, response: sanic.response.types.JSONResponse):
    """
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding
    """
    accept_encoding = request.headers.get("Accept-Encoding", "")
    accepted_encoding = {encoding.strip() for encoding in accept_encoding.split(",")}

    uncompressed_content_length = len(response.body)
    response_status = response.status
    content_type = response.content_type

    # NOTE
    # We're only supporting brotli compression at the moment so we'll just
    # verify if brotli is supported before using it. In the future if we want
    # more than brotli compression we'll have to verify it is supported and
    # what was selected.
    brotli_compression = COMPRESSION[0]

    compression_supported = brotli_compression in accepted_encoding
    content_type_supported = content_type in MIME_TYPES
    successful_status = response_status >= 200 and response_status < 300
    valid_minimum_size = (
        uncompressed_content_length is not None and uncompressed_content_length >= COMPRESSION_THRESHOLD
    )

    if compression_supported and content_type_supported and successful_status and valid_minimum_size:
        logger.debug("Attempting to compress the response body")
        try:
            compressed_body = brotli.compress(response.body)
        except Exception as gen_exp:
            logger.exception(compressed_body)
            logger.error("Unable to compress the response. Returning uncompressed response. Response: %s", response)
        else:
            compressed_content_length = len(compressed_body)
            logger.debug(
                "Successfully compressed response. uncompressed length %s | compressed length %s",
                uncompressed_content_length,
                compressed_content_length,
            )
            response.body = compressed_body
            response.headers["Content-Encoding"] = "br"
            response.headers["Content-Length"] = len(response.body)

    return response
