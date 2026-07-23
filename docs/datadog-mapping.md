# Catalogue → Datadog telemetry mapping

Source: *AI Observability — Datadog Implementation Addendum* — an internal source document, not published in this repo. This page shows how this demo's synthetic schema lines up with the addendum's telemetry contract, so the mock can become a real Datadog implementation without a schema rewrite — only a re-pointing of the ingestion layer.

**Positioning, per the addendum:** Datadog is the production observability/control *plane*, not the policy authority. Policy ownership stays with architecture, security, data governance and responsible-AI risk functions. This demo mirrors that: the synthetic guardrail spans record policy *decisions*, they do not implement policy.

## Telemetry object mapping

| Datadog telemetry object | Required attributes (addendum) | This demo's synthetic equivalent | File |
|---|---|---|---|
| **Workflow trace** | `workflow_id, ml_app, service, env, version, use_case, business_unit, tenant, channel, risk_tier, user_hash, session_id, outcome` | Same field set, generated 1:1 | `data/synthetic/raw/workflow_trace.csv` |
| **LLM span** | `provider, model, model_version, operation, prompt_version, temperature, input_tokens, output_tokens, total_tokens, cost, latency, status, finish_reason` | Same field set, incl. rate-limit error + fallback-model routing | `data/synthetic/raw/llm_span.csv` |
| **Retrieval span** | `retriever, index, query_type, top_k, source_ids, source_authority, source_freshness, retrieval_latency, relevance_score` | Same field set | `data/synthetic/raw/retrieval_span.csv` |
| **Tool span** | `tool_name, tool_version, action_type, read_or_write, risk_class, approval_required, approval_status, latency, status, error_type` | Same field set + a `cost_usd` field (tool/API cost) | `data/synthetic/raw/tool_span.csv` |
| **Guardrail/evaluation span** | `policy_name, policy_version, evaluator, score, threshold, allow_block_escalate, reason_code, reviewer_id` | Same field set | `data/synthetic/raw/guardrail_span.csv` |
| **Decision record** *(not in the original addendum table — added here per [`decision-contract.md`](decision-contract.md))* | `decision_id, decision_type, actor, objective, input_facts, evidence_refs, options_evaluated, selected_action, selection_basis, confidence, policy_evaluations, authority, tool_action, business_outcome, owner, risk_tier` | Same field set, one row per consequential decision, correlated by `workflow_id` | `data/synthetic/raw/decision_span.csv` |
| **Incident event** | `severity, affected_workflows, affected_users, root_cause_category, linked_trace_id, detection_source, mitigation, recurrence_flag` | Same field set | `data/synthetic/raw/incident_event.csv` |
| **Release/evaluation event** *(not in the original addendum table — added here)* | `event_id, event_type (release\|rollback), artefact, from_version, to_version, golden_set_accuracy_pct, regression_test_pass_rate_pct, canary_health` | New table, models a prompt-version rollout + rollback | `data/synthetic/raw/release_event.csv` |

## Dashboard pack mapping

The addendum specifies 7 dashboards. **All 7 are now implemented** as tabs in `dashboard/index.html` and as full JSON templates in `datadog/dashboards/`, plus an **8th — AI Decision Trace** — added to implement the decision-tracing capability ([`decision-contract.md`](decision-contract.md)).

| Datadog dashboard (addendum §7) | Status in this demo | Notes |
|---|---|---|
| AI Executive Health | ✅ Implemented — tab 1 | Workflow volume, success rate, cost/successful workflow, P95 latency, incidents, policy violations, tenant adoption |
| AI Engineering Operations | ✅ Implemented — tab 2 | Latency by layer, error/retry/timeout rate, rate-limit events, loop events, single-trace waterfall |
| AI Security and Responsible AI | ✅ Implemented — tab 3 | Prompt injection, sensitive data egress, toxicity flags, high-risk tool calls, approval bypasses |
| AI Cost and Capacity | ✅ Implemented — tab 4 | Token usage, cost by model, quota utilisation vs. an assumed daily quota, cumulative cost vs. an assumed monthly budget, fallback-model cost uplift |
| Agent Behaviour and Agency | ✅ Implemented — tab 5 (partial) | Step count, tool-call mix, escalation rate, tool-call success as a tool-selection-accuracy proxy. **Not modelled:** multi-agent handoffs, plan-revision count, critic/evaluator disagreement — this scenario is single-agent |
| RAG and Grounding Quality | ✅ Implemented — tab 6 (synthetic eval layer) | Retrieval hit rate, groundedness score, citation accuracy, hallucination rate, abstention rate, source freshness. Groundedness/citation-accuracy/hallucination/abstention are modelled as **synthetic evaluation-harness output**, not derived from raw retrieval spans — that distinction is the real architectural point: a production system needs an actual eval pipeline (LLM-as-judge + human review + golden sets) to produce these numbers |
| AI Release and Evaluation | ✅ Implemented — tab 7 | A seeded prompt v14→v15 release, regression detection, and rollback, with daily regression-pass-rate and golden-set-accuracy series and a release/rollback log |
| AI Decision Trace *(added — not in the addendum's original pack)* | ✅ Implemented — tab 8 (`ai-decision-trace.json`) | First-class decision records: inspectable record with evidence, options, selection basis, policy result, authority and business outcome; decisions-by-type, daily decisions vs. overrides, and a searchable decision table. Explainability and authority coverage computed from the records. **Rationale/confidence are illustrative in the mock** — agent-emitted in production (`decision-contract.md` §5) |

## Instrumentation standard

Per the addendum: instrument with Datadog's LLM/Agent Observability SDK where supported, and OpenTelemetry GenAI semantic conventions where cross-vendor portability is preferred. The synthetic span taxonomy in this repo (`workflow / llm / retrieval / tool / guardrail / decision`) mirrors the addendum's recommended span taxonomy (`workflow, agent, llm, retrieval, tool, guardrail, human_review, final_response`) so migrating the generator's field names into either SDK is a direct mapping exercise, not a redesign.

## What would change to go from mock → real

1. Replace `data/generator/*.py` with actual SDK/OTel instrumentation emitting the same field names into Datadog.
2. Replace `data/generator/aggregate_dashboard_summary.py` with real Datadog dashboard queries (the aggregation logic — daily P95, cost/successful-workflow, etc. — becomes the dashboard widget query definitions in `datadog/dashboards/`).
3. Replace the static `dashboard/` app with native Datadog dashboards built from `datadog/dashboards/*.json` (dashboards-as-code) — or keep this static app as an executive-facing summary view fed by the Datadog API instead of the local JSON file.
4. Wire `datadog/monitors/*.json` and `datadog/slos/*.json` to real alert channels (see `docs/roadmap.md`).
5. Stand up an actual evaluation harness (Datadog Managed/Custom Evaluations, an LLM-as-judge pipeline, golden sets, human review sampling) to produce the RAG/Grounding Quality and Release/Evaluation tabs' numbers for real — in this demo those are synthetic series generated directly by the aggregator, not derived from spans, which is intentionally the same separation a real implementation needs (production traces feed evals; evals don't run inline on every request).
