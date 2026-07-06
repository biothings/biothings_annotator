"""
Metadata routes
"""

import asyncio
import json as json_module
import logging
import time

import sanic
from sanic import json
from sanic.request import Request
from sanic.views import HTTPMethodView

logger = logging.getLogger(__name__)

ELASTICSEARCH_PROBE_HOST = "elasticsearch.es-core-components.svc.cluster.local"
ELASTICSEARCH_PROBE_PORT = 9200
ELASTICSEARCH_PROBE_PATH = "/_cluster/health"
ELASTICSEARCH_PROBE_TARGET = (
    f"http://{ELASTICSEARCH_PROBE_HOST}:{ELASTICSEARCH_PROBE_PORT}{ELASTICSEARCH_PROBE_PATH}"
)
ELASTICSEARCH_PROBE_TIMEOUT_SECONDS = 2.0


class VersionView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        self.default_headers = {"Cache-Control": "no-store"}

    def open_version_file(self):
        with open("version.txt", "r") as version_file:
            version = version_file.read().strip()
            return version

    async def probe_elasticsearch(self):
        result = {
            "target": ELASTICSEARCH_PROBE_TARGET,
            "reachable": False,
            "tcp_connect": False,
            "status_code": None,
            "cluster_status": None,
            "cluster_name": None,
            "elapsed_ms": None,
            "error": None,
        }
        writer = None
        started_at = time.perf_counter()

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ELASTICSEARCH_PROBE_HOST, ELASTICSEARCH_PROBE_PORT),
                timeout=ELASTICSEARCH_PROBE_TIMEOUT_SECONDS,
            )
            result["tcp_connect"] = True

            request = (
                f"GET {ELASTICSEARCH_PROBE_PATH} HTTP/1.1\r\n"
                f"Host: {ELASTICSEARCH_PROBE_HOST}\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            writer.write(request.encode("ascii"))
            await asyncio.wait_for(writer.drain(), timeout=ELASTICSEARCH_PROBE_TIMEOUT_SECONDS)

            status_line = await asyncio.wait_for(reader.readline(), timeout=ELASTICSEARCH_PROBE_TIMEOUT_SECONDS)
            status_parts = status_line.decode("ascii", errors="replace").split()
            if len(status_parts) >= 2:
                result["status_code"] = int(status_parts[1])
                result["reachable"] = True

            response_body = await asyncio.wait_for(reader.read(4096), timeout=ELASTICSEARCH_PROBE_TIMEOUT_SECONDS)
            _, _, body = response_body.partition(b"\r\n\r\n")
            if body:
                try:
                    cluster_health = json_module.loads(body.decode("utf-8"))
                except ValueError:
                    cluster_health = None
                if isinstance(cluster_health, dict):
                    result["cluster_status"] = cluster_health.get("status")
                    result["cluster_name"] = cluster_health.get("cluster_name")
        except Exception as exc:
            result["error"] = repr(exc)
        finally:
            result["elapsed_ms"] = int((time.perf_counter() - started_at) * 1000)
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        return result

    async def get(self, _: Request) -> json:
        """
        API versioning endpoint

        Leverages extracting a github commit hash from the annotator
        repository as the version to check the commit HEAD.
        Allows for verifying what the latest commit is on the live instance

        Will return {"version": "Unknown"} is unable to generate a hash
        """
        try:
            version = "Unknown"

            try:
                version = self.open_version_file()
            except FileNotFoundError:
                logger.error("The version.txt file does not exist.")
            except Exception as exc:
                logger.error(f"Error getting GitHub commit hash from version.txt file: {exc}")

            result = {"version": version, "elasticsearch_probe": await self.probe_elasticsearch()}
            return sanic.json(result, headers=self.default_headers)

        except Exception as exc:
            logger.error(f"Error getting GitHub commit hash: {exc}")
            result = {
                "version": "Unknown",
                "elasticsearch_probe": {
                    "target": ELASTICSEARCH_PROBE_TARGET,
                    "reachable": False,
                    "tcp_connect": False,
                    "status_code": None,
                    "cluster_status": None,
                    "cluster_name": None,
                    "elapsed_ms": None,
                    "error": repr(exc),
                },
            }
            return sanic.json(result)
