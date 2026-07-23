# AI Observability Metrics Catalogue — condensed reference

Source: *AI Observability Metrics Catalogue for Agentic LLM Workflows* (v1.0, 30 Jun 2026) — an internal source document, not published in this repo. This page condenses that document to the sections this demo implements; the full catalogue covers ~150 metrics across 13 dimensions.

## Architectural principle

Every AI decision, model call, tool action, policy decision and human override should be observable, attributable, explainable and governable. Implement AI observability as a **trace tree**, not isolated logs: a workflow trace connects user request → policy checks → context assembly → retrieval → planning → model calls → tool calls → evaluator checks → human approvals → final outcome.

The consequential decisions in that tree are now promoted to **first-class decision records** — inspectable objects with evidence, options, selection basis, policy result, authority and business outcome — rather than being inferred from adjacent spans. See [`decision-contract.md`](decision-contract.md) for the schema, governance rules and demonstrator backlog; this is the capability the [decision-tracing review](decision-contract.md) identified as the next maturity step.

## Reference alignment

| Reference | Use |
|---|---|
| [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Vendor-neutral traces, spans, metrics, model identity, token counts |
| [NIST AI Risk Management Framework 1.0](https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf) | Risk framing: valid/reliable, safe/secure/resilient, accountable/transparent, explainable, privacy-enhanced, fair |
| [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | Security controls: prompt injection, insecure output handling, sensitive info disclosure, model DoS, supply chain, excessive agency |
| [Datadog LLM/Agent Observability docs](https://docs.datadoghq.com/llm_observability/) | Implementation reference: traces, spans, evaluations, metrics, OTel ingestion |

## Top 20 priority metrics (start here before expanding to the full catalogue)

| # | Metric | Purpose | In this demo? |
|---|---|---|---|
| 1 | Cost per successful workflow | Economic viability | ✅ Executive tab |
| 2 | End-to-end workflow latency P95 | UX / SLA | ✅ Executive + Engineering tabs |
| 3 | Workflow success rate | Production reliability | ✅ Executive tab |
| 4 | LLM calls per workflow | Agent efficiency | ✅ raw data (`llm_call_count`) |
| 5 | Tool calls per workflow | Agency control | ✅ raw data (`tool_call_count`) |
| 6 | Input/output/reasoning token counts | Cost, latency, prompt bloat | ✅ raw LLM span data |
| 7 | Retry rate | Waste / instability | ✅ Engineering tab |
| 8 | Timeout rate | Dependency/orchestration failure | ⚠️ modelled via tool `error_type=timeout` only |
| 9 | Fallback rate | Model/tool degradation | ✅ raw data (fallback model on rate-limit days) |
| 10 | Rate-limit events | Provider quota/scaling risk | ✅ Engineering tab |
| 11 | Hallucination / groundedness score | Factual trust | ✅ RAG tab — **synthetic eval-harness series**, not derived from raw spans (see caveat below) |
| 12 | Citation accuracy | Source-backed integrity | ✅ RAG tab — same caveat as #11 |
| 13 | Prompt injection attempt rate | Adversarial pressure | ✅ Security tab |
| 14 | Sensitive data egress events | Privacy/confidentiality | ✅ Security tab |
| 15 | Unauthorised tool-call attempts | Excessive agency | ✅ Security tab (`policy_approval_bypasses`) |
| 16 | Human escalation rate | Automation boundary | ✅ raw data (`outcome=escalated_human`) + Agent Behaviour tab |
| 17 | Human override rate | Trust/quality proxy | 🟡 partially addressed — the decision record now captures `authority` (approval/override/bypass) per consequential decision (`decision-contract.md`); a human *editing the model output* is still not modelled |
| 18 | Policy violation count | Governance failure signal | ✅ Security + Executive tabs |
| 19 | Incident MTTD / MTTR | Operational readiness | ✅ Executive tab (incident log) |
| 20 | Model/prompt version regression score | Change/drift detection | ✅ Release & Evaluation tab — seeded v14→v15 regression + rollback |

Items marked ⛔ still require capability this demo doesn't model. Items marked ✅ with the "synthetic eval-harness series" caveat are a deliberate architectural point, not an oversight: groundedness, citation accuracy, hallucination flags, regression pass rate and golden-set accuracy are generated directly as a daily series in `data/generator/aggregate_dashboard_summary.py`, independent of the raw workflow/LLM/tool/retrieval spans — because in a real implementation these come from a **separate evaluation pipeline** (LLM-as-judge, golden sets, human review sampling) running on a schedule, not from live request tracing. That separation is exactly what you'd build in the real Weeks 7–10 phase (see [`roadmap.md`](roadmap.md)).

### Decision-tracing metrics (now computed from decision records)

The full catalogue lists *Explainability coverage* (% of decisions with a rationale/source) and *Policy decision traceability* under Responsible AI. Both are now **computed directly from the decision records** (`data/synthetic/raw/decision_span.csv`), not aspirational:

| Metric | Definition in this demo | Where |
|---|---|---|
| **Explainability coverage %** | decisions with a non-empty `selection_basis` **and** `evidence_refs`, over all consequential decisions | Decision Trace tab; `genai.decision.count{explainable:true}` |
| **Authority coverage %** | decisions with proven authority (approval not required, or an `approver_id` present) — guardrail overrides deliberately lower it | Decision Trace tab; `genai.decision.count{authority_proven:true}` |
| **Guardrail override count** | consequential decisions that proceeded without required review (`policy_result:bypass`) | Decision Trace tab + zero-tolerance monitor |

These close the gap the decision-tracing review flagged: the concept was designed in the series but not exposed as a first-class object. See [`decision-contract.md`](decision-contract.md).

## The 13 measurement dimensions (full catalogue)

Cost · Performance/latency · Scale/throughput/capacity · Reliability/resiliency · Agent-specific behaviour · RAG/retrieval/grounding · Security · Responsible AI · Incidents/operational risk · Model quality/drift/evaluation · Data/privacy/compliance · Change/release/governance · (Executive dashboard view spans all of the above.)

This demo implements **all 7 dashboards** from the addendum's full Datadog pack (see [`datadog-mapping.md`](datadog-mapping.md)) — starting from the catalogue's own §8 *"Practical dashboards to build"* shortlist (**Executive AI Service Health**, **Engineering Operations**, **Responsible AI and Security**) and extending into **Cost & Capacity**, **Agent Behaviour**, **RAG & Grounding**, and **Release & Evaluation**.

## Operating model (accountability layers)

| Layer | Accountability |
|---|---|
| Platform Engineering | Tracing, metrics, logging, latency, cost, quota, reliability, deployment observability |
| Cyber Security | Prompt injection, data leakage, tool abuse, supply-chain risk, detection engineering, incident response |
| Data Governance | Source authority, classification, residency, retention, approved-source controls, data minimisation |
| Responsible AI / Risk | Bias, fairness, explainability, human oversight, risk acceptance, model documentation, evaluation cadence |
| Product Owner | Business value, completion rate, adoption, user satisfaction, process impact |
| Architecture | Patterns, guardrails, integration controls, model/tool governance, reference architecture, investment cases |
