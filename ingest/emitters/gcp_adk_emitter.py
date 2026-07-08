#!/usr/bin/env python3
"""
Google Vertex AI / Gemini (ADK / Agent Engine) — sample contract emitter.

Real integration: ADK agents emit OTel natively (default sink: Cloud Trace via
telemetry.googleapis.com OTLP). Point the OTLP exporter at this repo's
Collector instead — no code change beyond exporter config:
  https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk
Your remaining job is the Rule-0 resource attributes (see contract_emitter.build_resource).

This sample fakes that emission so the pipeline can be tested end-to-end
without a GCP project:  python gcp_adk_emitter.py [--console]
"""
import sys
from contract_emitter import emit_workflow

PLATFORM = {
    "cloud.provider": "gcp",
    "cloud.platform": "gcp_vertex_ai",
    "gen_ai.provider.name": "gcp.vertex_ai",
}
LLM = {"provider": "gcp.vertex_ai", "model": "gemini-2.5-flash", "operation": "generate_content"}

if __name__ == "__main__":
    tid = emit_workflow(PLATFORM, LLM, console="--console" in sys.argv)
    print(f"[gcp-adk] emitted workflow trace {tid}")
