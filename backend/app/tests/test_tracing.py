"""OpenTelemetry tracing (spec §9).

Verified with an in-memory span exporter, so the instrumentation itself is
proven locally; only the export leg to a real OTLP collector / Grafana is
unverifiable in this environment.
"""
import os

import pytest

# Ensure we use an in-memory sqlite DB for tests
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.core.tracing import init_tracing, reset_tracing_provider_for_tests, tracing_enabled
from app.main import create_app
from app.models.users import db


@pytest.fixture
def traced_app():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    reset_tracing_provider_for_tests()
    app = create_app()
    exporter = InMemorySpanExporter()
    init_tracing(app, span_exporter=exporter)
    with app.app_context():
        db.create_all()
    yield app, exporter


def test_tracing_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    assert tracing_enabled() is False
    # A plain app gets no exporter attached.
    assert init_tracing(create_app()) is None


def test_a_request_produces_a_server_span(traced_app):
    app, exporter = traced_app
    resp = app.test_client().get("/", headers={"X-Request-ID": "trace-me"})
    assert resp.status_code == 200

    spans = exporter.get_finished_spans()
    assert spans, "no spans were produced for the request"
    span = spans[-1]
    assert span.attributes.get("http.method") in ("GET", None)
    # The correlation id used by the JSON request log is on the span too, so a
    # trace can be joined to its log line.
    assert span.attributes.get("request.id") == "trace-me"
