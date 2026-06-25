"""otel_setup.py — OpenTelemetry (OTLP/HTTP) export for the collapsed serving endpoints.

Shared by BOTH endpoints (agent-recs E1 and discovery-api E2) — it lives in E1's serving dir and is
bundled into each model artifact by both register.py files. It implements the H1.6 observability spec:
push metrics + traces to Grafana Cloud's managed OTLP gateway over HTTPS (Grafana cannot scrape a
serverless Model Serving endpoint, so the endpoint exports its own telemetry).

CONTRACT — telemetry is BEST-EFFORT and must NEVER break a request:
  * init() and every record_*/span helper swallow their own exceptions. If OTel deps are missing, the
    env is unset, or the push fails (e.g. a 401 from an expired token), serving continues unaffected.
  * Export failures (the silent-401 trap Satish warned about) are surfaced to STDOUT via a logging
    handler on the `opentelemetry` logger, so a dead token shows up in Databricks driver logs and can
    be alerted on — instead of telemetry vanishing silently.

ENV (set on the endpoint; see config.example.env / the deploy notebook):
  OTEL_EXPORTER_OTLP_ENDPOINT   Grafana Cloud OTLP gateway URL (SDK appends /v1/metrics, /v1/traces)
  OTEL_EXPORTER_OTLP_PROTOCOL   http/protobuf
  OTEL_EXPORTER_OTLP_HEADERS    Authorization=Basic%20<base64>   (percent-encoded space — NOT literal)
  OTEL_SERVICE_NAME             agent-recs | discovery-api
  OTEL_TRACES_SAMPLER_ARG       fraction of requests traced (e.g. 0.15); metrics stay at 100%

Metric labels are kept to BOUNDED sets only (endpoint, path, stage, dependency, status, error_type).
Raw query text / user ids are never used as labels (cardinality + PII) — they belong in logs.

TOKEN COUNTS: record_tokens() is wired but the router does not yet surface LLM usage (llm.py returns
text only). Until that is added, token metrics are simply not emitted (no fabricated values).
"""

import logging
import os
import sys
import threading

# Module state. Everything degrades to a no-op when _READY is False.
_READY = False
_LOCK = threading.Lock()
_TRACER = None
_M = {}                      # metric-name -> instrument
_SERVICE = "unknown-service"


def _log(msg: str):
    print(f"[otel] {msg}", flush=True)


def _wire_export_error_logging():
    """Route OTel's own export failures (401, connection refused, blocked egress) to stdout so they are
    visible in Databricks logs rather than failing silently."""
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("[otel-export] %(levelname)s %(name)s: %(message)s"))
    for name in ("opentelemetry.exporter.otlp", "opentelemetry.sdk.metrics",
                 "opentelemetry.sdk.trace.export"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.addHandler(h)


def init(service_name: str = None):
    """Build the Meter + Tracer providers with OTLP/HTTP exporters and define the metric instruments.
    Idempotent and best-effort: any failure leaves the module in no-op mode and serving continues."""
    global _READY, _TRACER, _SERVICE
    with _LOCK:
        if _READY:
            return
        if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
            _log("OTEL_EXPORTER_OTLP_ENDPOINT not set — telemetry disabled (no-op).")
            return
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            _SERVICE = service_name or os.getenv("OTEL_SERVICE_NAME", "agent-recs")
            resource = Resource.create({"service.name": _SERVICE})

            # Metrics — OTLP/HTTP exporter reads endpoint/headers/protocol from env automatically.
            reader = PeriodicExportingMetricReader(OTLPMetricExporter())
            metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
            meter = metrics.get_meter("feedsai.serving")

            # Traces — sample a fraction of normal traffic (errors get an ERROR status + a 100% metric).
            try:
                ratio = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.15"))
            except ValueError:
                ratio = 0.15
            tp = TracerProvider(resource=resource, sampler=ParentBased(TraceIdRatioBased(ratio)))
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(tp)
            _TRACER = trace.get_tracer("feedsai.serving")

            _build_instruments(meter)
            _wire_export_error_logging()
            _READY = True
            _log(f"initialized — service={_SERVICE}, trace_sample={ratio}, "
                 f"endpoint={os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')}")
        except Exception as e:                       # missing deps / bad config → stay no-op
            _log(f"init failed ({type(e).__name__}: {e}) — telemetry disabled, serving unaffected.")


def _build_instruments(meter):
    # Bounded-cardinality instruments per the H1.6 metric catalogue.
    _M["request_latency_ms"] = meter.create_histogram(
        "request_latency_ms", unit="ms", description="End-to-end request latency")
    _M["requests_total"] = meter.create_counter(
        "requests_total", description="Request count by status")
    _M["errors_total"] = meter.create_counter(
        "errors_total", description="Errors by classified type")
    _M["stage_latency_ms"] = meter.create_histogram(
        "stage_latency_ms", unit="ms", description="Per-stage latency (extract/establish/refine/rerank)")
    _M["llm_call_latency_ms"] = meter.create_histogram(
        "llm_call_latency_ms", unit="ms", description="Language-model call latency")
    _M["routing_path_total"] = meter.create_counter(
        "routing_path_total", description="Routing-path distribution")
    _M["extraction_total"] = meter.create_counter(
        "extraction_total", description="Intent-extraction outcomes (ok=true/false)")
    _M["result_count"] = meter.create_histogram(
        "result_count", description="Results returned per request")
    _M["empty_results_total"] = meter.create_counter(
        "empty_results_total", description="Requests that returned no results")
    _M["results_exact_total"] = meter.create_counter(
        "results_exact_total", description="Exact results returned")
    _M["results_related_total"] = meter.create_counter(
        "results_related_total", description="Related/backfill results returned")
    _M["llm_input_tokens_total"] = meter.create_counter(
        "llm_input_tokens_total", description="LLM input tokens (cost driver)")
    _M["llm_output_tokens_total"] = meter.create_counter(
        "llm_output_tokens_total", description="LLM output tokens (cost driver)")
    _M["dependency_latency_ms"] = meter.create_histogram(
        "dependency_latency_ms", unit="ms", description="Per-dependency latency")
    _M["dependency_calls_total"] = meter.create_counter(
        "dependency_calls_total", description="Per-dependency call count")
    _M["dependency_errors_total"] = meter.create_counter(
        "dependency_errors_total", description="Per-dependency error count")


def enabled() -> bool:
    return _READY


# ── metric helpers (all no-op + exception-safe unless init() succeeded) ──────────────────
def _add(name, value, attrs):
    if not _READY:
        return
    try:
        inst = _M.get(name)
        if inst is None:
            return
        (inst.add if hasattr(inst, "add") else inst.record)(value, attrs)
    except Exception:
        pass


def record_request(endpoint, latency_ms, status):
    _add("request_latency_ms", float(latency_ms), {"endpoint": endpoint})
    _add("requests_total", 1, {"endpoint": endpoint, "status": status})


def record_error(endpoint, error_type):
    _add("errors_total", 1, {"endpoint": endpoint, "error_type": error_type})


def record_stage_latencies(endpoint, breakdown):
    """`breakdown` is timing.snapshot(): {<cat>_ms, <cat>_calls, work_ms}. We emit one stage_latency_ms
    point per category, plus llm_call_latency_ms for the llm category."""
    if not _READY or not breakdown:
        return
    for key, val in breakdown.items():
        if not key.endswith("_ms") or key == "work_ms":
            continue
        stage = key[:-3]                              # strip "_ms"
        _add("stage_latency_ms", float(val), {"endpoint": endpoint, "stage": stage})
        if stage == "llm":
            _add("llm_call_latency_ms", float(val), {"endpoint": endpoint})


def record_routing(endpoint, path=None, extraction_ok=None,
                   result_count=None, exact=None, related=None):
    if path is not None:
        _add("routing_path_total", 1, {"endpoint": endpoint, "path": str(path)})
    if extraction_ok is not None:
        _add("extraction_total", 1, {"endpoint": endpoint, "ok": str(bool(extraction_ok)).lower()})
    if result_count is not None:
        _add("result_count", float(result_count), {"endpoint": endpoint})
        if result_count == 0:
            _add("empty_results_total", 1, {"endpoint": endpoint})
    if exact:
        _add("results_exact_total", int(exact), {"endpoint": endpoint})
    if related:
        _add("results_related_total", int(related), {"endpoint": endpoint})


def record_tokens(endpoint, input_tokens=None, output_tokens=None):
    if input_tokens:
        _add("llm_input_tokens_total", int(input_tokens), {"endpoint": endpoint})
    if output_tokens:
        _add("llm_output_tokens_total", int(output_tokens), {"endpoint": endpoint})


def record_dependency(dependency, latency_ms, error=False):
    _add("dependency_latency_ms", float(latency_ms), {"dependency": dependency})
    _add("dependency_calls_total", 1, {"dependency": dependency})
    if error:
        _add("dependency_errors_total", 1, {"dependency": dependency})


# ── tracing ──────────────────────────────────────────────────────────────────
class _NullSpan:
    def set_attribute(self, *a, **k): pass
    def set_status(self, *a, **k): pass
    def record_exception(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def span(name, attributes=None):
    """Context manager for a span. No-op (returns a null span) when telemetry is disabled. On exception
    inside the block, the span is marked ERROR and the exception recorded, then re-raised."""
    if not _READY or _TRACER is None:
        return _NullSpan()
    try:
        from opentelemetry.trace import StatusCode, Status

        class _Span:
            def __enter__(self_inner):
                self_inner._cm = _TRACER.start_as_current_span(name)
                self_inner._span = self_inner._cm.__enter__()
                if attributes:
                    for k, v in attributes.items():
                        if v is not None:
                            self_inner._span.set_attribute(k, v)
                return self_inner._span

            def __exit__(self_inner, exc_type, exc, tb):
                try:
                    if exc is not None:
                        self_inner._span.record_exception(exc)
                        self_inner._span.set_status(Status(StatusCode.ERROR, str(exc)))
                    return self_inner._cm.__exit__(exc_type, exc, tb)
                except Exception:
                    return False

        return _Span()
    except Exception:
        return _NullSpan()
