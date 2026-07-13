"""Tests for OpenTelemetry configuration handling."""

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
