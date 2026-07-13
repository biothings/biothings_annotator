"""OpenTelemetry tracing configuration for the Annotator web application."""

from __future__ import annotations

import importlib.util
import logging
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

from sanic import Sanic

logger = logging.getLogger(__name__)
_initialized_pid = None

DEFAULT_TELEMETRY_SETTINGS = {
    "OPENTELEMETRY_ENABLED": False,
    "OPENTELEMETRY_SERVICE_NAME": "BioThingsAnnotator",
    "OPENTELEMETRY_JAEGER_HOST": "http://localhost",
    "OPENTELEMETRY_JAEGER_PORT": 4318,
    "OPENTELEMETRY_EXCLUDED_URLS": ["^/$", "^/status$", "^/version$", "^/webapp", "^/favicon\\.ico$"],
}


def _environment_value(name: str, default: Any) -> Any:
    """Return an OpenTelemetry environment override, preserving useful types."""
    value = os.getenv(name)
    if value is None:
        return default
    if isinstance(default, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(value)
    if isinstance(default, Sequence) and not isinstance(default, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def telemetry_settings(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Apply OPENTELEMETRY_* environment variables to file configuration."""
    return {name: _environment_value(name, value) for name, value in configuration.items()}


def _initialize_worker_telemetry(settings):
    """Create the exporter lazily inside the worker handling the request."""
    global _initialized_pid
    current_pid = os.getpid()
    if _initialized_pid == current_pid:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = settings["endpoint"]
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: settings["service_name"]}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    _initialized_pid = current_pid
    logger.warning("OpenTelemetry worker is exporting traces to %s", endpoint)


async def _start_request_span(request):
    settings = request.app.ctx.opentelemetry_settings
    if any(re.search(pattern, request.path) for pattern in settings["excluded_urls"]):
        return
    _initialize_worker_telemetry(settings)
    from opentelemetry import propagate, trace

    span_context = trace.get_tracer(__name__).start_as_current_span(
        f"{request.method} {request.path}",
        context=propagate.extract(dict(request.headers)),
        kind=trace.SpanKind.SERVER,
        attributes={
            "http.request.method": request.method,
            "url.path": request.path,
            "url.scheme": request.scheme,
            "server.address": request.host.split(":", 1)[0],
        },
    )
    request.ctx.opentelemetry_span_context = span_context
    span_context.__enter__()


async def _finish_request_span(request, response):
    span_context = getattr(request.ctx, "opentelemetry_span_context", None)
    if span_context is None:
        return
    from opentelemetry import trace

    span = trace.get_current_span()
    span.set_attribute("http.response.status_code", response.status)
    if response.status >= 500:
        span.set_status(trace.Status(trace.StatusCode.ERROR))
    span_context.__exit__(None, None, None)


def configure_telemetry(application: Sanic, configuration: Mapping[str, Any]) -> bool:
    """Instrument Sanic and HTTPX and export traces to Jaeger over OTLP/HTTP."""
    configured_values = {**DEFAULT_TELEMETRY_SETTINGS, **configuration}
    settings = telemetry_settings(configured_values)
    if not settings.get("OPENTELEMETRY_ENABLED", False):
        logger.info("OpenTelemetry is disabled")
        return False

    if importlib.util.find_spec("opentelemetry.sdk") is None:
        logger.warning("OpenTelemetry is enabled but its SDK is not installed")
        return False

    host = str(settings.get("OPENTELEMETRY_JAEGER_HOST", "http://localhost")).rstrip("/")
    port = int(settings.get("OPENTELEMETRY_JAEGER_PORT", 4318))
    endpoint = f"{host}:{port}/v1/traces"
    excluded_urls = settings.get("OPENTELEMETRY_EXCLUDED_URLS", [])
    if not isinstance(excluded_urls, str):
        excluded_urls = ",".join(excluded_urls)

    application.ctx.opentelemetry_settings = {
        "endpoint": endpoint,
        "service_name": settings.get("OPENTELEMETRY_SERVICE_NAME", "BioThingsAnnotator"),
        "excluded_urls": [pattern for pattern in excluded_urls.split(",") if pattern],
    }
    application.register_middleware(_start_request_span, "request")
    application.register_middleware(_finish_request_span, "response")
    return True
