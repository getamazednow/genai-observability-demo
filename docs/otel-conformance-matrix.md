# OTel GenAI conformance matrix — the telemetry contract, pinned

This document freezes this repo's telemetry contract against the
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
so that spans emitted by **Azure AI Foundry**, **Google Vertex AI / Gemini (ADK / Agent Engine)**
and **AWS Bedrock AgentCore** — all of which emit OTel GenAI natively — land in one shape,
light up the mock dashboard via `ingest/bridge/`, and flow into
[Datadog LLM Observability](https://docs.datadoghq.com/llm_observability/instrumentation/otel_instrumentation/)
without a schema rewrite.

**Pinned semconv baseline: v1.37** — the first version Datadog LLM Observability ingests
natively (auto-mapping `gen_ai.*` to its own schema). The GenAI conventions are still
*incubating*: re-validate this matrix on every semconv upgrade before rolling it out.

## Rule 0 — the tags the hyperscalers will NOT give you

Platform SDKs emit model/token/latency attributes. They do **not** emit this repo's
governance dimensions. These MUST be set as **OTel resource attributes** at the
application level, and the Collector rejects/flags spans without them
(see `ingest/collector/otel-collector-config.yaml`):

| Contract field (workflow_trace.csv) | Resource attribute | Source |
|---|---|---|
| `ml_app` | `gen_ai.demo.ml_app` | app-set (custom) |
| `service` | `service.name` | standard OTel |
| `env` | `deployment.environment.name` | standard OTel |
| `version` | `service.version` | standard OTel |
| `use_case` | `gen_ai.demo.use_case` | app-set (custom) |
| `business_unit` | `gen_ai.demo.business_unit` | app-set (custom) |
| `tenant` | `gen_ai.demo.tenant` | app-set (custom) |
| `channel` | `gen_ai.demo.channel` | app-set (custom) |
| `risk_tier` | `gen_ai.demo.risk_tier` | app-set (custom) |

`gen_ai.demo.*` is this repo's private namespace for attributes the semconv does not
define. When the semconv later standardises an equivalent, migrate and update this row.

## Span-level mapping

### workflow_trace.csv ← root (workflow) span

| CSV column | OTel source | Notes |
|---|---|---|
| `workflow_id` | `trace_id` | one workflow = one trace |
| `user_hash` | `gen_ai.demo.user_hash` | app-set; hash **before** emission |
| `session_id` | `gen_ai.conversation.id` | semconv |
| `start_ts` | span `start_time_unix_nano` | |
| `outcome` | `gen_ai.demo.outcome` | app-set: resolved \| escalated_human \| blocked_policy \| failed |
| `total_latency_ms` | root span duration | |
| `total_cost_usd`, `llm_cost_usd`, `tool_cost_usd`, `retrieval_cost_usd` | derived by pipeline | cost is **not** in semconv; summed from child spans by the bridge (or by Datadog natively) |
| `llm_call_count`, `tool_call_count`, `step_count`, `loop_count` | derived by pipeline | counted from child spans; `loop_count` via `gen_ai.demo.loop` marker |

### llm_span.csv ← spans with `gen_ai.operation.name` = `chat` (or `generate_content`)

| CSV column | OTel source | Notes |
|---|---|---|
| `provider` | `gen_ai.provider.name` | semconv |
| `model` | `gen_ai.request.model` | semconv |
| `model_version` | `gen_ai.response.model` | semconv |
| `operation` | `gen_ai.operation.name` | semconv |
| `prompt_version` | `gen_ai.demo.prompt_version` | custom — release/rollback storyline depends on it |
| `temperature` | `gen_ai.request.temperature` | semconv |
| `input_tokens` / `output_tokens` | `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | semconv |
| `total_tokens` | derived (sum) | |
| `cost_usd` | `gen_ai.demo.cost_usd` or pipeline-derived | custom; Datadog computes cost natively for known models |
| `latency_ms` | span duration | |
| `status` | span status (+ `error.type`) | `rate_limited` via `error.type=429` |
| `finish_reason` | `gen_ai.response.finish_reasons[0]` | semconv (array) |

### tool_span.csv ← spans with `gen_ai.operation.name` = `execute_tool`

| CSV column | OTel source | Notes |
|---|---|---|
| `tool_name` | `gen_ai.tool.name` | semconv |
| `tool_version` | `gen_ai.demo.tool_version` | custom |
| `action_type`, `read_or_write`, `risk_class`, `approval_required`, `approval_status` | `gen_ai.demo.tool.*` | custom — the governance heart of the contract; no semconv equivalent yet |
| `latency_ms` / `status` / `error_type` | span duration / status / `error.type` | |
| `cost_usd` | `gen_ai.demo.cost_usd` | custom |

### retrieval_span.csv ← spans with `gen_ai.operation.name` = `retrieve` (custom op)

Semconv has no retrieval schema yet; the whole block is `gen_ai.demo.retrieval.*`
(`retriever`, `index`, `query_type`, `top_k`, `source_ids`, `source_authority`,
`source_freshness_days`, `relevance_score`, `retrieval_hit`, `cost_usd`).
Eval-harness columns (`groundedness_score`, `citation_accuracy_score`,
`hallucination_flag`, `abstention_flag`) are **not** emitted by request spans —
they come from the scheduled evaluation pipeline (see repo caveat) and are left
empty by the bridge.

### guardrail_span.csv ← spans with `gen_ai.operation.name` = `guardrail` (custom op)

Entirely `gen_ai.demo.guardrail.*` (`policy_name`, `policy_version`, `evaluator`,
`score`, `threshold`, `allow_block_escalate`, `reason_code`, `reviewer_id`).
No semconv equivalent; deliberate — policy decisions are recorded, not implemented.

### incident_event.csv / release_event.csv — not span data

These are **events**, not traces: in production they come from the incident tooling
and CI/CD (Datadog Events API / monitors), not the OTLP span pipeline. The bridge
writes header-only CSVs so the aggregator contract holds.

## Per-platform emission notes

| Platform | Emits | Path to this Collector |
|---|---|---|
| Azure AI Foundry (Agent Framework / SK / LangGraph) | OTel GenAI semconv | point OTLP exporter at the Collector (in addition to / instead of App Insights) |
| Vertex AI / Gemini — ADK, Agent Engine | OTel natively | swap `telemetry.googleapis.com` exporter for Collector OTLP endpoint |
| AWS Bedrock AgentCore (ADOT) | OTel-compatible | set `OTEL_EXPORTER_OTLP_ENDPOINT` to the Collector; CloudWatch GenAI dashboard optional in parallel |

Platform-level metrics (quota, throttling, billing) bypass this pipeline — they arrive
via Datadog's native AWS/Azure/GCP integrations (see `docs/datadog-mapping.md`).

## Datadog note

Datadog LLM Observability natively maps `gen_ai.request.model`, `gen_ai.usage.*`,
`gen_ai.provider.name`, `gen_ai.operation.name`, finish reasons and latency from
OTLP with no code changes. The `gen_ai.demo.*` custom attributes arrive as span
tags — the dashboard queries in `datadog/dashboards/` filter on them. Watch tag
cardinality: `tenant`/`use_case`/`risk_tier` are bounded sets by design; never
promote `user_hash` or `session_id` to metric tags.
