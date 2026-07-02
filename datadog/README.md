# Datadog migration kit (templates — not connected to a live account)

This folder is the bridge from the synthetic mock in `/dashboard` to a real Datadog implementation. Nothing here calls a live Datadog API; these are **illustrative dashboards-as-code templates and monitor/SLO definitions** written in Datadog's JSON schema conventions, using a proposed metric namespace (`genai.*`) and tag taxonomy consistent with `docs/datadog-mapping.md`.

When you're ready to implement for real:

1. Stand up instrumentation (Datadog LLM/Agent Observability SDK or OpenTelemetry GenAI semantic conventions) emitting the fields listed in `docs/datadog-mapping.md`.
2. Adapt the metric names in these JSON files to whatever your instrumentation actually emits (LLM Observability auto-generates many of these; custom metrics use the `genai.*` names below as a starting convention).
3. Import via `dashboards/*.json` → Datadog UI "Import dashboard JSON", or via Terraform (`datadog_dashboard` resource) / the Dashboards API.
4. Import `monitors/*.json` similarly via the Monitors API or `datadog_monitor` Terraform resource, and connect `notify` targets to your real on-call channel.
5. Wire `slos/*.json` to the corresponding monitors as SLO time-slices.

## Proposed metric namespace

| Metric | Type | Key tags |
|---|---|---|
| `genai.workflow.count` | count | `outcome, use_case, tenant, channel, risk_tier` |
| `genai.workflow.latency_ms` | distribution | `use_case, tenant` |
| `genai.workflow.cost_usd` | distribution | `use_case, tenant, cost_category` (`llm`\|`tool`\|`retrieval`) |
| `genai.llm.call.count` | count | `provider, model, status, finish_reason` |
| `genai.llm.latency_ms` | distribution | `provider, model` |
| `genai.llm.tokens` | distribution | `provider, model, token_type` (`input`\|`output`) |
| `genai.tool.call.count` | count | `tool_name, risk_class, status` |
| `genai.tool.latency_ms` | distribution | `tool_name` |
| `genai.guardrail.decision.count` | count | `policy_name, allow_block_escalate, reason_code` |
| `genai.incident.count` | count | `severity, root_cause_category` |
| `genai.workflow.step_count` | distribution | `use_case, tenant` |
| `genai.retrieval.count` | count | `retriever, hit (bool)` |
| `genai.retrieval.source_freshness_days` | distribution | `retriever` |
| `genai.eval.groundedness_score` | gauge | `use_case` — from evaluation harness, not raw traces |
| `genai.eval.citation_accuracy_score` | gauge | `use_case` — from evaluation harness |
| `genai.eval.hallucination_flag` | count | `use_case` — from evaluation harness |
| `genai.eval.abstention_flag` | count | `use_case` — from evaluation harness |
| `genai.eval.regression_pass_rate` | gauge | `artefact` (`prompt`\|`model`) — from scheduled eval run |
| `genai.eval.golden_set_accuracy` | gauge | `artefact` — from scheduled eval run |
| `genai.release.event` | count | `event_type` (`release`\|`rollback`), `artefact, from_version, to_version` |
| `genai.release.active_prompt_version` | gauge (tag value) | `use_case` |

## Contents

- `dashboards/` — one JSON file per dashboard in the addendum's 7-dashboard pack. All 7 are now fully specified and flagged `"status": "implemented_in_demo"`, matching the 7 tabs in `/dashboard`. `agent-behaviour-and-agency.json` and `rag-and-grounding-quality.json` carry a `"caveat"` field calling out what this v1 single-agent, non-LLM-judge scenario still doesn't model (multi-agent handoffs; a real eval harness) — see `docs/roadmap.md`.
- `monitors/` — alert definitions for the SLOs/alert policies in the addendum §8.
- `slos/` — SLO objects referencing the monitors.
