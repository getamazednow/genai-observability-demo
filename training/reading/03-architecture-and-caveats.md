# 3. Architecture choices, caveats and constraints

Honesty about scope is the point of this repository. This page is the single place that consolidates every architectural choice, every known gap, and every caveat that should be carried into a board or risk-committee conversation — so nothing here is discovered for the first time in a harder room later.

## Core architectural choice: trace tree, not logs

Per the metrics catalogue's architectural principle, every workflow is instrumented as **one connected trace tree**: user request → policy checks → context assembly → retrieval → planning → model calls → tool calls → evaluator checks → human approvals → final outcome. See the [trace-tree architecture diagram](../diagrams/exports/01-trace-tree-architecture.png) below.

This single choice is what makes cross-dimensional correlation possible — the same `workflow_id` that shows up as a cost line in the Executive tab is the same trace that shows a policy bypass in the Security tab. Isolated logs cannot do this; a trace tree can.

## Positioning: Datadog is a plane, not a policy

Per the addendum: **Datadog is the production observability/control plane, not the policy authority.** Policy ownership stays with architecture, security, data governance and responsible-AI risk functions. This demo mirrors that split deliberately — the synthetic guardrail spans record policy *decisions* (allow/block/escalate), they do not implement policy. That distinction matters in governance conversations: buying an observability tool does not discharge the accountability for setting the policy in the first place.

## The single most important caveat: synthetic evaluation-harness series

Groundedness, citation accuracy, hallucination rate, abstention rate, regression pass rate and golden-set accuracy are all present in the RAG and Release dashboards. They are generated as a **synthetic daily series**, independent of the raw workflow/LLM/tool/retrieval spans — this is deliberate, and it mirrors exactly how a real implementation has to work: evals run on a schedule against sampled traffic (an LLM-as-judge pipeline, golden sets, human review sampling), not inline on every request. Present this as an honest architectural point, not a hidden shortcut: **a real eval harness is still required to produce these numbers for real** (scoped into Weeks 7–10 of the roadmap).

## Other known gaps in this v1 (by design)

| Gap | Why it isn't modelled | Where it's tracked |
|---|---|---|
| A real evaluation harness (LLM-as-judge, human review pipeline) | Needs actual model/human infrastructure a synthetic demo can't credibly fake | Roadmap Weeks 7–10 |
| Multi-agent behaviour (handoffs, plan-revision count, critic/evaluator disagreement) | This scenario is deliberately single-agent | Flagged in `datadog/dashboards/agent-behaviour-and-agency.json` |
| Bias/fairness flags, refusal quality, human override rate | No concept of a human editing or overriding an AI output exists in this scenario yet | `docs/metrics-catalogue.md` |
| Ground-truth tool-selection accuracy | Tool-call success rate is used as a proxy instead | Agent Behaviour tab, tab 5 |
| Timeout rate as a distinct signal | Only modelled via tool `error_type=timeout`, not as its own top-level metric | Metrics catalogue, priority-metrics table |

None of these are oversights — they require capability (a real eval pipeline, multi-agent orchestration, human-review UX) that a synthetic-data demo cannot honestly fabricate. Calling them out explicitly is what separates a credible reference architecture from a demo that oversells itself.

## Caveats to carry into the real build (from the addendum, §10)

These are the six caveats the source addendum explicitly flags, and they should travel with this material into any real implementation conversation:

- **Don't overstate Datadog's market position.** Cite only what's evidenced (supported providers/frameworks) — not "used by every frontier lab."
- **Observability ≠ governance.** Datadog operationalises controls; policy ownership stays with security/governance/risk/product, not the tooling vendor.
- **Prompt/output logging is a privacy decision, not a default.** Apply redaction, hashing, classification and retention classes by risk tier *before* logging real content — this needs to be decided before instrumenting live traffic, not after.
- **Standardise tags before scaling.** High-cardinality raw IDs as primary dimensions get expensive and noisy fast; agree the tag taxonomy in Weeks 0–2, not retrofit it later.
- **AI evaluations are probabilistic controls.** Pair LLM-as-judge scoring with human review, golden sets and deterministic policy checks for anything high-stakes — don't treat an eval score as a compliance control on its own.
- **Auto-instrumentation won't cover everything.** Proprietary orchestration or unsupported frameworks need manual spans/OpenTelemetry instrumentation — budget for this explicitly rather than assuming SDK coverage is complete.

## Ownership model (accountability layers)

Per the metrics catalogue, six functions each hold a distinct accountability slice. This should be assigned by name before any real workflow is instrumented — the addendum is explicit that observability tooling operationalises controls, it does not replace accountable risk ownership.

| Layer | Accountability |
|---|---|
| Platform Engineering | Tracing, metrics, logging, latency, cost, quota, reliability, deployment observability |
| Cyber Security | Prompt injection, data leakage, tool abuse, supply-chain risk, detection engineering, incident response |
| Data Governance | Source authority, classification, residency, retention, approved-source controls, data minimisation |
| Responsible AI / Risk | Bias, fairness, explainability, human oversight, risk acceptance, model documentation, evaluation cadence |
| Product Owner | Business value, completion rate, adoption, user satisfaction, process impact |
| Architecture | Patterns, guardrails, integration controls, model/tool governance, reference architecture, investment cases |

## Reference standards this repository aligns to

| Reference | Use |
|---|---|
| [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Vendor-neutral traces, spans, metrics, model identity, token counts |
| [NIST AI Risk Management Framework 1.0](https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf) | Risk framing: valid/reliable, safe/secure/resilient, accountable/transparent, explainable, privacy-enhanced, fair |
| [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | Security controls: prompt injection, insecure output handling, sensitive info disclosure, model DoS, supply chain, excessive agency |
| [Datadog LLM/Agent Observability docs](https://docs.datadoghq.com/llm_observability/) | Implementation reference: traces, spans, evaluations, metrics, OTel ingestion |

## Related diagrams

**Diagram — observability trace-tree architecture:**

![Observability trace-tree architecture](../diagrams/exports/01-trace-tree-architecture.png)

**Diagram — target Datadog implementation architecture:**

![Target Datadog implementation architecture](../diagrams/exports/06-datadog-implementation-architecture.png)
