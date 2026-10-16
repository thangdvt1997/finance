"""OpenTelemetry tối thiểu cho api-gateway: span cho request FastAPI -> asyncpg (DB) / redis / httpx (proxy tới service nội bộ).

TẮT MẶC ĐỊNH (no-op): chỉ bật khi có biến OTEL_EXPORTER_OTLP_ENDPOINT (compose đặt http://jaeger:4318 khi chạy lớp ops).
Không có Jaeger/collector thì gateway vẫn chạy bình thường (export lỗi chỉ ghi log mức thấp, không chặn request: BatchSpanProcessor chạy nền).
Lấy mẫu: parent-based + tỉ lệ OTEL_TRACES_SAMPLER_ARG (mặc định 0,25) để chi phí gần như 0. Không đưa /healthz /readyz /metrics vào trace.
Import trễ trong hàm: thiếu gói opentelemetry thì bỏ qua (test/đường chạy khác không bị ảnh hưởng)."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("gateway.tracing")


def setup_tracing(app) -> bool:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if not endpoint or os.getenv("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError as e:  # noqa: BLE001
        log.warning("OTEL_EXPORTER_OTLP_ENDPOINT đặt nhưng thiếu gói opentelemetry (%s) — bỏ qua tracing", e)
        return False
    try:
        ratio = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.25"))
    except ValueError:
        ratio = 0.25
    provider = TracerProvider(
        resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "api-gateway"), "service.namespace": "tradingsys"}),
        sampler=ParentBased(TraceIdRatioBased(max(0.0, min(1.0, ratio)))),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # endpoint/header lấy từ biến OTEL_EXPORTER_OTLP_*
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics,/v1/stream,/v1/rt")   # WS: span cho MỌI khung gửi tốn ~10% CPU event loop (hub realtime)
    AsyncPGInstrumentor().instrument()
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    log.info("tracing bật: %s (mẫu %.0f%%)", endpoint, ratio * 100)
    return True
