#!/usr/bin/env python3
"""
Shared contract emitter — builds one synthetic agentic workflow as an
OTel GenAI span tree that conforms to docs/otel-conformance-matrix.md:

    workflow (root)
    ├── chat            (gen_ai.operation.name=chat)
    ├── retrieve        (custom op, gen_ai.demo.retrieval.*)
    ├── execute_tool    (gen_ai.tool.*, gen_ai.demo.tool.*)
    └── guardrail       (custom op, gen_ai.demo.guardrail.*)

The three platform emitters (azure_/gcp_/aws_) supply platform-flavoured
resource attributes and model names, then call emit_workflow(). In a real
integration this file disappears — the platform SDK (Agent Framework, ADK,
AgentCore/ADOT) emits these spans natively; only the resource attributes
in build_resource() remain your job.

Requires:  pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
Usage:     emit_workflow(resource_attrs, llm) — exports OTLP/HTTP to
           OTEL_EXPORTER_OTLP_ENDPOINT (default http://localhost:4318).
           Pass console=True to print spans instead (no Collector needed).
"""
import hashlib
import os
import time
import uuid

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def build_resource(platform_attrs: dict) -> dict:
    """Contract (Rule 0) resource attributes + platform flavour."""
    contract = {
        "service.name": "order-support-assistant",
        "service.version": "1.4.2",
        "deployment.environment.name": "demo",
        "gen_ai.demo.ml_app": "order-support-returns",
        "gen_ai.demo.use_case": "retail_support",
        "gen_ai.demo.business_unit": "digital_retail",
        "gen_ai.demo.tenant": "brand_a",
        "gen_ai.demo.channel": "web_chat",
        "gen_ai.demo.risk_tier": "medium",
    }
    contract.update(platform_attrs)
    return contract


def emit_workflow(platform_attrs: dict, llm: dict, console: bool = False) -> str:
    resource = Resource.create(build_resource(platform_attrs))
    provider = TracerProvider(resource=resource)
    exporter = ConsoleSpanExporter() if console else OTLPSpanExporter(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318") + "/v1/traces"
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    tracer = provider.get_tracer("genai-observability-demo.contract-emitter")

    session = str(uuid.uuid4())
    user_hash = hashlib.sha256(b"demo-user@example.com").hexdigest()[:16]

    with tracer.start_as_current_span("workflow") as wf:
        wf.set_attribute("gen_ai.conversation.id", session)
        wf.set_attribute("gen_ai.demo.user_hash", user_hash)
        wf.set_attribute("gen_ai.demo.outcome", "resolved")

        with tracer.start_as_current_span("retrieve") as r:
            r.set_attribute("gen_ai.operation.name", "retrieve")
            r.set_attribute("gen_ai.demo.retrieval.retriever", "orders_kb")
            r.set_attribute("gen_ai.demo.retrieval.index", "orders-v3")
            r.set_attribute("gen_ai.demo.retrieval.query_type", "hybrid")
            r.set_attribute("gen_ai.demo.retrieval.top_k", 5)
            r.set_attribute("gen_ai.demo.retrieval.source_authority", "approved")
            r.set_attribute("gen_ai.demo.retrieval.source_freshness_days", 2)
            r.set_attribute("gen_ai.demo.retrieval.relevance_score", 0.91)
            r.set_attribute("gen_ai.demo.retrieval.retrieval_hit", True)
            r.set_attribute("gen_ai.demo.cost_usd", 0.0002)
            time.sleep(0.01)

        with tracer.start_as_current_span("chat") as c:
            c.set_attribute("gen_ai.operation.name", llm.get("operation", "chat"))
            c.set_attribute("gen_ai.provider.name", llm["provider"])
            c.set_attribute("gen_ai.request.model", llm["model"])
            c.set_attribute("gen_ai.response.model", llm.get("model_version", llm["model"]))
            c.set_attribute("gen_ai.request.temperature", 0.2)
            c.set_attribute("gen_ai.usage.input_tokens", 812)
            c.set_attribute("gen_ai.usage.output_tokens", 204)
            c.set_attribute("gen_ai.response.finish_reasons", ["stop"])
            c.set_attribute("gen_ai.demo.prompt_version", "v15")
            c.set_attribute("gen_ai.demo.cost_usd", 0.0041)
            time.sleep(0.02)

        with tracer.start_as_current_span("execute_tool") as t:
            t.set_attribute("gen_ai.operation.name", "execute_tool")
            t.set_attribute("gen_ai.tool.name", "order_status_lookup")
            t.set_attribute("gen_ai.demo.tool_version", "2.1.0")
            t.set_attribute("gen_ai.demo.tool.action_type", "lookup")
            t.set_attribute("gen_ai.demo.tool.read_or_write", "read")
            t.set_attribute("gen_ai.demo.tool.risk_class", "low")
            t.set_attribute("gen_ai.demo.tool.approval_required", False)
            t.set_attribute("gen_ai.demo.tool.approval_status", "not_required")
            t.set_attribute("gen_ai.demo.cost_usd", 0.0001)
            time.sleep(0.01)

        with tracer.start_as_current_span("guardrail") as g:
            g.set_attribute("gen_ai.operation.name", "guardrail")
            g.set_attribute("gen_ai.demo.guardrail.policy_name", "output_sensitive_data_scan")
            g.set_attribute("gen_ai.demo.guardrail.policy_version", "3")
            g.set_attribute("gen_ai.demo.guardrail.evaluator", "deterministic")
            g.set_attribute("gen_ai.demo.guardrail.score", 0.02)
            g.set_attribute("gen_ai.demo.guardrail.threshold", 0.5)
            g.set_attribute("gen_ai.demo.guardrail.allow_block_escalate", "allow")
            g.set_attribute("gen_ai.demo.guardrail.reason_code", "clean")

        trace_id = format(wf.get_span_context().trace_id, "032x")

    provider.shutdown()  # flush
    return trace_id


if __name__ == "__main__":
    import sys
    tid = emit_workflow(
        {"cloud.provider": "local", "gen_ai.provider.name": "demo"},
        {"provider": "demo", "model": "demo-model"},
        console="--console" in sys.argv,
    )
    print(f"emitted workflow trace {tid}")
