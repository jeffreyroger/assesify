"""OpenTelemetry tracing (spec §9).

Off by default and opt-in via `OTEL_ENABLED`, so the existing request path,
tests and local dev are untouched unless tracing is explicitly asked for.

Exporter selection:

* `OTEL_EXPORTER_OTLP_ENDPOINT` set -> OTLP/HTTP exporter (the real deployment
  target; a collector is not available in this environment, so that half is
  configured but unverified).
* otherwise -> a `ConsoleSpanExporter`, which makes tracing fully verifiable
  locally without any collector.
* callers may pass their own exporter (the test suite passes an in-memory one).

Spans carry the same `X-Request-ID` correlation id that `app/main.py` already
puts on every request and log line, so a trace can be joined to its log.
"""
import os

_PROVIDER_INITIALIZED = False


def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def tracing_enabled():
    return _truthy(os.environ.get("OTEL_ENABLED", "0"))


def init_tracing(app, span_exporter=None):
    """Instrument `app` for tracing. Returns the exporter in use, or None.

    Import errors and misconfiguration are swallowed deliberately: tracing must
    never be the reason the API fails to start.
    """
    global _PROVIDER_INITIALIZED

    if span_exporter is None and not tracing_enabled():
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError:  # pragma: no cover - optional dependency
        app.logger.warning("OTEL_ENABLED is set but opentelemetry is not installed.")
        return None

    exporter = span_exporter
    simple = span_exporter is not None
    if exporter is None:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter()
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()
            simple = True

    if not _PROVIDER_INITIALIZED:
        resource = Resource.create({
            SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "assesify-backend"),
        })
        trace.set_tracer_provider(TracerProvider(resource=resource))
        _PROVIDER_INITIALIZED = True

    processor = (SimpleSpanProcessor(exporter) if simple else BatchSpanProcessor(exporter))
    trace.get_tracer_provider().add_span_processor(processor)

    def _request_hook(span, environ):
        request_id = environ.get("HTTP_X_REQUEST_ID")
        if span is not None and span.is_recording() and request_id:
            span.set_attribute("request.id", request_id)

    FlaskInstrumentor().instrument_app(app, request_hook=_request_hook)
    return exporter


def reset_tracing_provider_for_tests():
    """Allow a second test to install its own provider."""
    global _PROVIDER_INITIALIZED
    _PROVIDER_INITIALIZED = False
