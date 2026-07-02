# GenAI Project Observability — Demo Dashboard

A reference architecture and working demo for observing agentic Gen AI workflows in production — what to measure, why it matters, and how to operationalise it on Datadog. Built entirely on **synthetic data**; not connected to any live system.

> **Status:** mock / portfolio reference. Purpose: demonstrate an observability approach for architecture-board, risk-committee and CoP review ahead of a real Datadog implementation.

## Why this exists

Agentic Gen AI workflows fail in ways conventional APM doesn't catch: a "successful" response can still hide excessive cost, weak grounding, a policy bypass, unauthorised tool use, or poor human-review coverage. This repo shows a concrete, minimum-viable observability model for that class of system — cost, reliability, performance, agent behaviour, security and responsible-AI risk in one place, correlated by trace.

It's built from two internal source documents (kept private, not published in this repo — condensed content is included below):

- **AI Observability Metrics Catalogue for Agentic LLM Workflows** (v1.0) — the *what to measure and govern* baseline: ~150 metrics across 13 dimensions, condensed in [`docs/metrics-catalogue.md`](docs/metrics-catalogue.md).
- **AI Observability — Datadog Implementation Addendum** — the *how to implement it* companion: telemetry contract, dashboard pack, SLOs, 90-day roadmap, mapped in [`docs/datadog-mapping.md`](docs/datadog-mapping.md) and [`docs/roadmap.md`](docs/roadmap.md).

## The demo scenario

**Order Support & Returns Assistant** — an agentic retail customer-service workflow (order status, returns, refunds, loyalty credits, address changes) operating across three storefront brands, over a synthetic 30-day window. Chosen because it exercises every dimension that matters for a governance demo: cost at scale, tool-driven side effects (refunds = money movement), and a believable attack surface (prompt injection against a refund tool).

Three storylines are deliberately seeded into the data so the dashboards show a diagnosable signal, not noise:

| Event | What happened | Why it's here |
|---|---|---|
| **REL-2026-0608 / REL-2026-0609** | A prompt version bump (v14 → v15) degraded groundedness and citation accuracy; caught by the (synthetic) evaluation harness and rolled back ~27 hours later | Demonstrates the Release & Evaluation dashboard's core job: catching a regression before it becomes a quality incident, and showing the eval-gate → rollback loop |
| **INC-2026-0611** (Sev2) | A cluster of prompt-injection attempts targeting the `refund_issue` tool; guardrail caught 92%, a handful bypassed | Demonstrates the security dashboard's core job: catching an adversarial pattern and quantifying what got through |
| **INC-2026-0621** (Sev1) | A promo-driven traffic surge triggered provider rate-limiting, forcing retries and fallback-model routing, spiking latency and cost | Mirrors Datadog's own published finding that provider rate limits are a material share of production LLM failures |

## What's in the dashboard

All 7 dashboards from the addendum's Datadog pack, starting from the catalogue's own "practical dashboards to build" shortlist (the first 3) and extending through the rest:

1. **Executive AI Health** — workflow volume, success rate, cost per successful workflow, monthly run-rate, estimated cost avoidance vs. a human-handled equivalent, P95 latency, incident log, policy violations.
2. **Engineering Operations** — latency decomposed by layer (model/retrieval/tool), P50/P95/P99 trend, error/retry rate, rate-limit events, agent loop events, a representative single-trace waterfall.
3. **Security & Responsible AI** — prompt injection attempts (blocked vs. bypassed), sensitive-data egress, toxicity flags, high-risk tool calls, policy-approval bypasses, and an incident spotlight.
4. **Cost & Capacity** — token usage, cost by model, quota utilisation against an assumed daily quota, cumulative cost vs. an assumed monthly budget, fallback-model cost uplift.
5. **Agent Behaviour** — average steps/tool calls per workflow, tool-call mix, escalation rate, tool-call success rate as a tool-selection-quality proxy.
6. **RAG & Grounding** — retrieval hit rate, groundedness, citation accuracy, hallucination rate, abstention rate, source freshness.
7. **Release & Evaluation** — regression pass rate, golden-set accuracy, canary health, and the release/rollback log.

Dashboards 6 and 7 are the ones worth reading the fine print on: their quality scores (groundedness, citation accuracy, hallucination flags, regression pass rate, golden-set accuracy) are generated as a **synthetic evaluation-harness series**, independent of the raw request spans — deliberately, because that's how a real implementation works too (evals run on a schedule against sampled traffic, not inline on every request). See [`docs/datadog-mapping.md`](docs/datadog-mapping.md) for the full caveat.

### Headline numbers from the current synthetic run

| Metric | Value |
|---|---|
| Workflows (30d) | ~5,100 |
| Success rate | ~95% |
| Cost per successful workflow | ~$0.025 |
| Forecasted monthly AI run-rate | ~$120 (against a $150 assumed budget) |
| Estimated monthly cost avoidance vs. human-handled equivalent* | ~$31,400 |
| Incidents | 2 (1 Sev1, 1 Sev2) + 1 release rollback |

<sub>*Illustrative only — assumes a $6.50 fully-loaded cost per human-handled contact, a modelling assumption for this demo, not a sourced benchmark. Regenerate the data (below) to reproduce exact figures.</sub>

## Repo structure

```
genai-observability-demo/
├── README.md
├── LICENSE
├── docs/
│   ├── metrics-catalogue.md       — condensed measurement/governance reference
│   ├── datadog-mapping.md         — catalogue → Datadog telemetry contract mapping
│   └── roadmap.md                 — 90-day path to production, annotated against this repo
├── data/
│   ├── generator/                 — Python: generates synthetic trace-tree telemetry + aggregates it
│   └── synthetic/
│       ├── raw/                   — span-level CSVs (workflow, LLM, retrieval, tool, guardrail, incident, release event)
│       └── (dashboard summary is written to dashboard/data/)
├── dashboard/                     — static HTML/CSS/JS app (GitHub Pages-ready), Chart.js via CDN
│   └── data/dashboard_summary.json — pre-aggregated daily rollup the dashboard reads
├── datadog/                       — dashboards-as-code + monitor/SLO templates for the real implementation
│   ├── dashboards/
│   ├── monitors/
│   └── slos/
├── training/                      — training material: reading guide, architecture diagrams, slide decks
│   ├── README.md                  — facilitator guide / suggested use by audience
│   ├── reading/                   — deep-dive narrative, one topic per file
│   ├── diagrams/                  — 6 architecture diagrams (Mermaid source + PNG exports)
│   ├── docx/                      — consolidated Word training guide
│   └── slides/                    — Exec Overview + Technical Deep-Dive PowerPoint decks
└── scripts/
    └── bootstrap-github-issues.sh — creates the initial Issues backlog (mock-to-real migration phases)
```

## Running it

No build step, no server-side code, no dependencies beyond Python 3 (stdlib only) for the generator and a browser for the dashboard.

**Regenerate the synthetic data:**
```bash
cd data/generator
python3 generate_synthetic_data.py        # writes data/synthetic/raw/*.csv
python3 aggregate_dashboard_summary.py    # writes dashboard/data/dashboard_summary.json
```

**View the dashboard:**
```bash
cd dashboard
python3 -m http.server 8000
# open http://localhost:8000
```
(Browsers block `fetch()` of local JSON over `file://`, so serve it — or publish via GitHub Pages, which works out of the box since `dashboard/` is fully static.)

## Known gaps in this v1 (by design)

All 7 dashboards are built, but a few things remain intentionally unmodelled because they need capability a synthetic-data demo can't credibly fake:

- **A real evaluation harness.** Groundedness, citation accuracy, hallucination/abstention rate, regression pass rate and golden-set accuracy are all present in the RAG and Release dashboards — but as a synthetic series, not something derived from an actual LLM-as-judge or human-review pipeline. That's the honest state of things until a real eval harness is stood up (Weeks 7–10 in the roadmap).
- **Multi-agent behaviour.** This scenario is single-agent, so handoffs, plan-revision count and critic/evaluator disagreement aren't modelled — see the caveat in `datadog/dashboards/agent-behaviour-and-agency.json`.
- **Bias/fairness flags, refusal quality, human override rate.** No concept of a human editing or overriding an AI output exists in this scenario yet.

These are called out explicitly in [`docs/metrics-catalogue.md`](docs/metrics-catalogue.md) and scoped into the Weeks 7–10 phase of [`docs/roadmap.md`](docs/roadmap.md) — they're real production requirements, not oversights.

## Path to a real implementation

See [`docs/roadmap.md`](docs/roadmap.md) for the full 90-day plan and [`docs/datadog-mapping.md`](docs/datadog-mapping.md) for exactly which fields/dashboards carry over unchanged. Short version: the synthetic schema *is* the target telemetry contract — moving to production means replacing the Python generator with real instrumentation (Datadog LLM/Agent Observability SDK or OpenTelemetry GenAI semantic conventions) emitting the same field names, and importing `/datadog`'s dashboard-as-code templates instead of reading local JSON.

## Sources

- *AI Observability Metrics Catalogue for Agentic LLM Workflows*, v1.0, 30 Jun 2026
- *AI Observability — Datadog Implementation Addendum*, 30 Jun 2026
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [NIST AI Risk Management Framework 1.0](https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Datadog LLM Observability docs](https://docs.datadoghq.com/llm_observability/)

## License

MIT — see [`LICENSE`](LICENSE).
