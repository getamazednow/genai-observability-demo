# 6. If Claude Code were to build the production infrastructure

This page is a **build plan and prompt spec**, written so it can be handed directly to Claude Code (or a comparable engineering agent) to execute the mock-to-real migration described in [`04-roadmap-and-next-steps.md`](04-roadmap-and-next-steps.md) and [`05-datadog-implementation-reference.md`](05-datadog-implementation-reference.md). It is scoped, phased, and gated with explicit human checkpoints — an agent should not be handed live API keys, money-movement tooling, or alert-routing configuration without a named human approving each gate.

## Operating principles for the agent

- **The synthetic schema is the target contract.** Do not redesign the telemetry schema; re-point it. Every field name in `data/synthetic/raw/*.csv` and `docs/datadog-mapping.md` should appear, unchanged, in the real instrumentation.
- **No live credentials in the agent's default context.** API keys, Datadog org access, PagerDuty/Slack tokens and any provider (OpenAI/Anthropic/Bedrock) credentials should be supplied only for the specific phase that needs them, via the human operator's own secrets management — never committed, never requested in chat.
- **Every phase ends with a human review gate**, not a merge-and-move-on. This mirrors the addendum's explicit point: observability tooling operationalises controls, it does not replace accountable ownership.
- **Additive, reversible changes.** Each phase should be a mergeable, revertable unit of work — no phase should require a later phase to be safe to ship.

## Phase 0 — Preflight (human-only, before any agent work starts)

Not delegable to an agent. Complete before Phase 1 begins:

- Named owner assigned per accountability layer (see [`03-architecture-and-caveats.md`](03-architecture-and-caveats.md)).
- Risk tier defined for the pilot workflow, and a redaction/retention policy signed off by data governance and legal.
- Datadog org provisioned with LLM Observability + APM entitlements; least-privilege service account created for the agent's CI pipeline (dashboards/monitors/SLOs import only — not full org admin).
- Approved model/tool registry for the pilot workflow.

## Phase 1 — Instrumentation scaffold (agent-executable, sandboxed)

**Goal:** replace `data/generator/generate_synthetic_data.py` with real instrumentation code, without touching production traffic yet.

Prompt-ready task for the agent:
> Using `docs/datadog-mapping.md` as the field-level contract, scaffold Datadog LLM/Agent Observability SDK (or OpenTelemetry GenAI semantic-convention) instrumentation for the Order Support & Returns Assistant workflow. Emit spans for `workflow`, `llm`, `retrieval`, `tool` and `guardrail` matching the exact field names in `data/synthetic/raw/*.csv`. Do not connect to a live Datadog org yet — write to local OTLP export or console exporter for validation. Include unit tests asserting every required field from the telemetry contract table is present on each span type.

**Human gate:** review that span field names match the contract 1:1 before any real ingestion is enabled; confirm no prompt/output content is logged unredacted.

## Phase 2 — Ingestion wiring (agent-executable, requires scoped credentials)

**Goal:** point the Phase 1 instrumentation at a real (non-production) Datadog environment.

Prompt-ready task:
> Wire the Phase 1 instrumentation to the Datadog Agent or OTel Collector, using the staging Datadog org credentials provided via [operator's secrets mechanism]. Validate that `genai.workflow.count`, `genai.llm.call.count`, `genai.tool.call.count` and `genai.guardrail.decision.count` (see the metric namespace table in `05-datadog-implementation-reference.md`) appear in Datadog's Metrics Explorer within 5 minutes of a test workflow run. Do not point at the production Datadog org.

**Human gate:** confirm staging data looks correct before promoting the same config to production; confirm redaction is actually being applied to any logged content, not just planned.

## Phase 3 — Dashboards, monitors, SLOs (agent-executable)

**Goal:** replace the local-JSON static dashboard with native Datadog dashboards, and make the monitor/SLO definitions live.

Prompt-ready task:
> Import all 7 templates in `datadog/dashboards/*.json` into the staging Datadog org via the Dashboards API or `datadog_dashboard` Terraform resource, adapting metric names in each JSON to whatever Phase 1/2 instrumentation actually emits (auto-generated LLM Observability metrics vs. the `genai.*` custom convention). Import `datadog/monitors/*.json` and `datadog/slos/*.json` similarly. Leave all monitor `notify` targets pointed at a staging Slack channel, not the real on-call rotation.

**Human gate:** platform engineering validates dashboard queries against known-good staging traffic; only then is a second PR opened to re-point `notify` targets at the real on-call rotation (`@pagerduty-genai-oncall`, `@security-oncall`) — this re-pointing should be its own reviewed change, not bundled into the import.

## Phase 4 — Governance and evaluation harness (largely NOT agent-executable)

**Goal:** close the single biggest gap this repo is explicit about — replace the synthetic evaluation-harness series with a real one.

This phase is mostly infrastructure decisions and vendor/build choices a human team needs to make (Datadog Managed Evaluations vs. custom LLM-as-judge pipeline, golden-set curation, human-review sampling rate and reviewer assignment). An agent's role here is narrower and should be scoped explicitly:

Prompt-ready task (narrow, supporting role only):
> Scaffold the plumbing to call [chosen evaluation service] on a scheduled basis against sampled production traffic, and emit `genai.eval.groundedness_score`, `genai.eval.citation_accuracy_score`, `genai.eval.hallucination_flag`, `genai.eval.regression_pass_rate` and `genai.eval.golden_set_accuracy` (see metric namespace table) in the same shape the RAG and Release dashboards already expect. Do not select the evaluation methodology or curate golden sets — that decision belongs to Responsible AI/Risk and Data Governance.

**Human gate:** Responsible AI/Risk signs off on the evaluation methodology before its output is used to gate any release (i.e., before regression-pass-rate is wired into an actual release-blocking check).

## Phase 5 — Scale and reusability (Weeks 11–13 equivalent)

**Goal:** extract this single-use-case implementation into a reusable instrumentation library and onboarding pattern.

Prompt-ready task:
> Extract the Phase 1–3 instrumentation, dashboard templates and monitor/SLO templates into a versioned internal package (or shared repo) with parameterised `use_case`, `tenant` and `risk_tier` values, and write an onboarding checklist a second team could follow without platform-engineering hand-holding. Do not change the underlying telemetry contract while doing this — this phase is about packaging, not schema redesign.

**Human gate:** a second, genuinely different use case attempts onboarding using only the checklist, with platform engineering observing but not intervening — if intervention is needed, the checklist has a gap.

## What an agent should never be handed unsupervised in this build

- Direct write access to a production Datadog org, production on-call rotation config, or production alert-routing — these should always be a reviewed PR, never a direct API call from an autonomous session.
- Money-movement tooling (refund/purchase tool credentials) in any context beyond the sandboxed/staging environment used for testing.
- The decision of what counts as an acceptable evaluation methodology or golden-set composition — this is a Responsible AI/Risk governance decision, not an engineering implementation detail.
- Redaction/retention policy definition — the agent implements the policy a human has already decided; it should not be asked to decide what's sensitive.

## Suggested sequencing summary

| Phase | Agent-executable? | Maps to roadmap horizon |
|---|---|---|
| 0 — Preflight | No (human-only) | Weeks 0–2 prerequisite |
| 1 — Instrumentation scaffold | Yes, sandboxed | Weeks 0–2 |
| 2 — Ingestion wiring | Yes, scoped credentials | Weeks 0–2 |
| 3 — Dashboards/monitors/SLOs | Yes, staging-only until gated | Weeks 3–6 |
| 4 — Governance/eval harness | Partially (plumbing only) | Weeks 7–10 |
| 5 — Scale/reusability | Yes, with acceptance test | Weeks 11–13 |

## Related diagrams

**Diagram — phased sequencing maps to the mock-to-real migration and roadmap already introduced in this guide** (see `04-roadmap-and-next-steps.md` and `05-datadog-implementation-reference.md` for the full-size versions of the mock-to-real migration and Datadog architecture diagrams).
