#!/usr/bin/env python3
"""
Azure AI Foundry — sample contract emitter.

Real integration: Microsoft Agent Framework / Semantic Kernel / LangGraph on
Foundry emit OTel GenAI spans natively; configure the OTLP exporter to point
at this repo's Collector (instead of, or in addition to, App Insights):
  https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-framework
Your remaining job is the Rule-0 resource attributes (see contract_emitter.build_resource).

This sample fakes that emission so the pipeline can be tested end-to-end
without an Azure subscription:  python azure_foundry_emitter.py [--console]
"""
import sys
from contract_emitter import emit_workflow

PLATFORM = {
    "cloud.provider": "azure",
    "cloud.platform": "azure_ai_foundry",
    "gen_ai.provider.name": "azure.ai.openai",
}
LLM = {"provider": "azure.ai.openai", "model": "gpt-4o-mini", "model_version": "gpt-4o-mini-2024-07-18"}

if __name__ == "__main__":
    tid = emit_workflow(PLATFORM, LLM, console="--console" in sys.argv)
    print(f"[azure-foundry] emitted workflow trace {tid}")
