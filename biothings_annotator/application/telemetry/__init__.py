"""
Integrates opentelemetry tracing with the biothings-annotator
web service
"""

import opentelemetry
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import sanic
from tracing import instrument_app


def instrument_application_telemetry(application_instance: sanic.Sanic):
    """
    Method integrating the opentelemetry into the annotator
    web service
    """
    opentelemetry_configuration = application_instance.config.get("opentelemetry", {})
    opentelemetry_enabled = opentelemetry_configuration.get("OPENTELEMETRY_ENABLED", False)

    if opentelemetry_enabled:
        opentelemetry_jaeger_host = opentelemetry_configuration["OPENTELEMETRY_JAEGER_HOST"]
        opentelemetry_jaeger_port = opentelemetry_configuration["OPENTELEMETRY_JAEGER_PORT"]
        opentelemetry_service_name = opentelemetry_configuration["OPENTELEMETRY_SERVICE_NAME"]

        jaeger_trace_exporter = JaegerExporter(
            agent_host_name=opentelemetry_jaeger_host,
            agent_port=opentelemetry_jaeger_port,
            udp_split_oversized_batches=True,
        )
        service_resource = Resource.create({SERVICE_NAME: opentelemetry_service_name})

        trace_provider = TracerProvider(resource=service_resource)
        batch_span_processor = BatchSpanProcessor(jaeger_trace_exporter)
        trace_provider.add_span_processor(batch_span_processor)
        opentelemetry.trace.set_tracer_provider(trace_provider)
        tracer = opentelemetry.trace.get_tracer("biothings-annotator")
        instrument_app(application_instance, tracer)
