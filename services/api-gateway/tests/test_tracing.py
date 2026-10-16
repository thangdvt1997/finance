from api_gateway.tracing import setup_tracing


def test_tracing_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert setup_tracing(object()) is False


def test_tracing_disabled_flag(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert setup_tracing(object()) is False
