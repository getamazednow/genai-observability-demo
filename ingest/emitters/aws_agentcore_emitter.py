#!/usr/bin/env python3
"""
AWS Bedrock AgentCore — sample contract emitter.

Real integration: AgentCore emits OTel-compatible telemetry via ADOT
(default sink: CloudWatch GenAI Observability). Set
OTEL_EXPORTER_OTLP_ENDPOINT to this repo's Collector — AgentCore telemetry
integrates with any OTLP backend without a custom shim:
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html
Your remaining job is the Rule-0 resource attributes (see contract_emitter.build_resource).

This sample fakes that emission so the pipeline can be tested end-to-end
without an AWS account:  python aws_agentcore_emitter.py [--console]
"""
import sys
from contract_emitter import emit_workflow

PLATFORM = {
    "cloud.provider": "aws",
    "cloud.platform": "aws_bedrock_agentcore",
    "gen_ai.provider.name": "aws.bedrock",
}
LLM = {"provider": "aws.bedrock", "model": "anthropic.claude-sonnet-5", "model_version": "claude-sonnet-5-v1"}

if __name__ == "__main__":
    tid = emit_workflow(PLATFORM, LLM, console="--console" in sys.argv)
    print(f"[aws-agentcore] emitted workflow trace {tid}")
