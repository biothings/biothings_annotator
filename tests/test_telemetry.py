"""Tests for OpenTelemetry configuration and request filtering."""

from types import SimpleNamespace

import pytest

from biothings_annotator.application import telemetry
from biothings_annotator.application.telemetry import telemetry_settings


def test_telemetry_settings_uses_file_defaults(monkeypatch):
    monkeypatch.delenv("OPENTELEMETRY_ENABLED", raising=False)
    configuration = {"OPENTELEMETRY_ENABLED": False, "OPENTELEMETRY_JAEGER_PORT": 4318}

    assert telemetry_settings(configuration) == configuration


def test_telemetry_settings_accepts_environment_overrides(monkeypatch):
    monkeypatch.setenv("OPENTELEMETRY_ENABLED", "true")
    monkeypatch.setenv("OPENTELEMETRY_JAEGER_PORT", "4319")
    monkeypatch.setenv("OPENTELEMETRY_EXCLUDED_URLS", "^/$, ^/status$")
    configuration = {
        "OPENTELEMETRY_ENABLED": False,
        "OPENTELEMETRY_JAEGER_PORT": 4318,
        "OPENTELEMETRY_EXCLUDED_URLS": [],
    }

    assert telemetry_settings(configuration) == {
        "OPENTELEMETRY_ENABLED": True,
        "OPENTELEMETRY_JAEGER_PORT": 4319,
        "OPENTELEMETRY_EXCLUDED_URLS": ["^/$", "^/status$"],
    }


def _request(path, route):
    settings = {"excluded_urls": ["^/status$"]}
    return SimpleNamespace(
        app=SimpleNamespace(ctx=SimpleNamespace(opentelemetry_settings=settings)),
        ctx=SimpleNamespace(),
        route=route,
        path=path,
    )


@pytest.mark.asyncio
async def test_start_request_span_ignores_unmatched_routes(monkeypatch):
    initialize = lambda settings: pytest.fail("telemetry should not be initialized")
    monkeypatch.setattr(telemetry, "_initialize_worker_telemetry", initialize)

    await telemetry._start_request_span(_request("/does-not-exist", None))


@pytest.mark.asyncio
async def test_start_request_span_applies_exclusions_after_route_match(monkeypatch):
    initialize = lambda settings: pytest.fail("telemetry should not be initialized")
    monkeypatch.setattr(telemetry, "_initialize_worker_telemetry", initialize)

    await telemetry._start_request_span(_request("/status", object()))
