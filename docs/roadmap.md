# 90-day path to production capability

Source: *AI Observability — Datadog Implementation Addendum*, §5 — an internal source document, not published in this repo. This is the addendum's roadmap, annotated with where this repo currently sits against it.

| Time horizon | Goal | Core activities | Exit criteria | This repo's status |
|---|---|---|---|---|
| **Weeks 0–2: Foundation** | Establish standards and one observable pilot | Define AI telemetry contract, tag taxonomy, data retention policy, redaction policy, risk tiers, approved model/tool registry, first instrumented workflow | One agentic workflow visible end-to-end with model spans, tool spans, token/cost/latency metrics and basic monitors | ✅ **Done in mock form.** Telemetry contract defined and matched to the addendum (`docs/datadog-mapping.md`); one workflow (Order Support & Returns Assistant) fully instrumented — as synthetic data, not live traffic |
| **Weeks 3–6: Operate** | Move from traces to operational control | Build dashboards for cost, latency, reliability, rate limits, agent loops, tool failures, safety evals; add SLOs, alert thresholds, runbooks, incident routing | Production support can detect, triage and assign AI workflow incidents via the platform, not manual log inspection | ✅ **Done in mock form.** All 7 dashboards built (`dashboard/` + `datadog/dashboards/`); SLO/monitor *definitions* stubbed (`datadog/`) but not wired to a real alerting channel; three seeded storylines (release regression, prompt-injection cluster, rate-limit cascade) demonstrate the detection→triage narrative but are not live |
| **Weeks 7–10: Govern** | Operationalise responsible AI and security controls | Integrate Sensitive Data Scanner/DLP, prompt-injection signals, custom evaluations, human-review telemetry, audit evidence, high-risk tool approval metrics | High-risk workflows have policy-decision telemetry, audit evidence, approval/override tracking, responsible AI dashboards | 🟡 **Partially done.** Guardrail/policy-decision telemetry, approval-bypass tracking, and a mocked evaluation-harness series (groundedness, citation accuracy, hallucination/abstention rate, regression pass rate, golden-set accuracy) are all modelled. **Still not modelled:** a *real* eval harness (LLM-as-judge, human review sampling), bias/fairness flags, refusal quality, human override rate — see `docs/metrics-catalogue.md` for the exact remaining gap list |
| **Weeks 11–13: Scale** | Create reusable platform patterns | Publish instrumentation library/templates, service onboarding checklist, golden dashboards, SLO templates, cost-allocation model, release-gate criteria | Second/third use cases onboard with materially less effort; governance and operations patterns are reusable | ⛔ **Not started.** This repo is a single-use-case reference; extracting it into a reusable instrumentation library is the next phase once a real workflow is live |

## Suggested production SLOs (from the addendum, §8) — targets to carry into the real implementation

| SLO / alert | Initial target | Notes |
|---|---|---|
| Workflow success rate | ≥ 98% for low/medium-risk workflows; higher for critical workflows | Define success by business outcome, not HTTP 200 / "LLM responded" |
| P95 end-to-end latency | Use-case specific; separate targets for interactive chat vs. batch agents | Break down into model, retrieval, tool, queue, orchestration latency |
| Cost per successful workflow | Budget threshold by use case and business unit | Alert when cost rises faster than successful completions |
| Rate-limit error rate | Alert on sustained provider rate-limit spikes or approaching quota threshold | Datadog's State of AI Engineering analysis found rate limits are a material share of observed LLM failures — this demo's seeded Sev1 incident (`INC-2026-0621`) is modelled on exactly this failure mode |
| Agent loop/fan-out control | Hard stop after a defined step count, repeated tool sequence, or fan-out threshold | Treat a breach as both a reliability *and* cost-risk event |
| Sensitive-data egress | Zero tolerance for confirmed credential/secret/protected-data leakage | Block, redact, escalate per severity |
| High-risk action without approval | Zero tolerance | Covers write/delete/send/purchase/financial/HR/production actions |
| Evaluation freshness | Re-run evals on every prompt/model/tool/policy change and on a scheduled cadence | Modelled at the narrative level (`REL-2026-0608`/`REL-2026-0609` in the release log show an eval-triggered rollback), but the underlying eval scores are a synthetic series — a real eval harness is still required |

## Ownership model to carry forward

Architecture, Platform Engineering, Cyber Security, Data Governance, Responsible AI/Risk, and Product Owner each hold a distinct accountability slice — see `docs/metrics-catalogue.md` for the full table. When this moves from mock to real, assign a named owner per layer before instrumenting live traffic; the addendum is explicit that observability tooling operationalises controls, it does not replace accountable risk ownership.

## Caveats to carry into the real build (from the addendum, §10)

- Don't overstate Datadog's market position — cite only what's evidenced (supported providers/frameworks), not "used by every frontier lab."
- Observability ≠ governance. Datadog operationalises controls; policy ownership stays with security/governance/risk/product.
- Prompt/output logging is a privacy decision, not a default — apply redaction, hashing, classification and retention classes by risk tier before logging real content.
- Standardise tags before scaling; high-cardinality raw IDs as primary dimensions get expensive and noisy fast.
- AI evaluations are probabilistic controls — pair LLM-as-judge with human review, golden sets and deterministic policy checks for anything high-stakes.
- Auto-instrumentation won't cover proprietary orchestration or unsupported frameworks — plan for manual spans/OTel there.
