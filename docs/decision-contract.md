# Decision Contract — promoting decisions to first-class trace objects

Source: *Decision Tracing in the AI Observability Control Plane* (capability assessment, 21 Jul 2026) — a review of this repo and the published AI observability series. This page is the **workshop pre-read**: it turns that review's recommendation into an agreed schema, lifecycle, governance ruleset, and a prioritised demonstrator backlog, so the design session can leave with decisions, not discussion.

> **Status: PROPOSAL — not yet implemented.** Nothing in `data/`, `dashboard/`, or `datadog/` emits a decision object today. This document defines the target so the build (step 2) is a mechanical exercise, not a redesign. It is deliberately written in the same "honest about mock vs. real" style as the rest of `docs/`.

---

## 1. Why this exists

The current demonstrator answers **"what happened?"** — the trace waterfall in `dashboard/app.js` decomposes a workflow into guardrail → retrieval → LLM → tool → guardrail spans, principally by latency and execution order. It does **not** answer **"why was *this* action selected over the alternatives available to the agent?"**

That second question is the definition of *decision tracing*, and it is already intrinsic to the series' architecture — the source Metrics Catalogue already lists *"Explainability coverage — % of decisions with rationale, source"* and *"Policy decision traceability"* as target metrics. The gap is not concept; it is that the demonstrator infers the decision from adjacent spans rather than exposing it as an object an investigator can open.

**Design principle (unchanged from `metrics-catalogue.md`):** implement observability as a trace tree, not isolated logs. A decision is a **new node in that existing tree**, correlated by `workflow_id` — not a parallel system.

### One honest re-framing of the review

The review scores *policy evaluation* as "partial" and *human approval* as "aggregate." In the raw data they are richer than that implies: `guardrail_span.csv` already carries per-workflow `policy_name, policy_version, allow_block_escalate, reviewer_id`, and `tool_span.csv` already carries per-call `approval_required, approval_status`. So the per-decision policy and authority signals **largely already exist in the telemetry** — they are simply not correlated into a decision object or surfaced in the UI. That makes this a **data-model-correlation + investigator-experience change, not a net-new telemetry-capture problem** — cheaper and lower-risk than a first read of the maturity table suggests. The genuinely absent fields are the *choice* fields: options considered, selected action, selection basis, and per-decision confidence.

---

## 2. What counts as a "decision" (scope)

Not every span is a decision. A decision is traced when it is **consequential** — it selects an action from more than one permitted option and has a business or governance effect. The workshop must agree the in-scope list; the proposed default for the retail scenario:

| Decision type | Triggered when | Consequential because |
|---|---|---|
| `refund_eligibility` | agent chooses approve / reject / escalate on a refund | moves money; policy-bounded |
| `high_risk_tool_invocation` | agent selects a `write`/`high` risk-class tool (`refund_issue`, `address_update`) | mutates customer/account state |
| `escalation_vs_autoresolve` | agent chooses to escalate to a human vs. resolve autonomously | sets the automation boundary |
| `guardrail_override` | a flagged action proceeds after review/approval | governance-critical; must be provable |

Explicitly **out of scope** (execution, not decision): pure `read` lookups, retries, formatting steps. These remain ordinary spans and become *evidence* the decision points to.

---

## 3. The decision schema

Namespaced `gen_ai.demo.decision.*` (this repo's private namespace for attributes the OTel GenAI semconv does not yet define — same rule as `otel-conformance-matrix.md` Rule 0). Join key is `workflow_id`, identical to every other table. New synthetic file: `data/synthetic/raw/decision_span.csv`.

| Field | Type | Mandatory | Notes / correlation |
|---|---|---|---|
| `decision_id` | string `DEC-YYYY-NNNN` | ✅ | stable primary key |
| `workflow_id` | string | ✅ | FK → `workflow_trace.csv` (the system of record) |
| `ts` | ISO-8601 | ✅ | decision timestamp |
| `decision_type` | enum (§2) | ✅ | drives search + retention class |
| `actor_type` | enum `agent\|human\|system` | ✅ | who/what decided |
| `actor_name` | string | ✅ | e.g. `returns-resolution-agent` |
| `actor_version` | string | ✅ | version the decision was made under (for replay) |
| `objective` | string | ✅ | e.g. `approve_customer_refund` |
| `input_facts` | json | ✅ | e.g. `{order_value, customer_tier, claim_age_days}` — redaction class applies |
| `evidence_refs` | list | ✅ | IDs of `retrieval_span` rows / `source_ids` that informed it |
| `evidence_freshness_days` | int | ⚪ | from correlated retrieval span |
| `groundedness_score` | float | ⚪ | from correlated eval series |
| `options_evaluated` | list | ✅ | **the choice set** — the permitted actions considered |
| `selected_action` | string | ✅ | the option taken |
| `selection_basis` | list | ✅ | concise, structured reasons (see §5 boundary) |
| `confidence` | float 0–1 | ⚪ | **only if the model/agent actually emits it** (see §5) |
| `policy_evaluations` | list | ✅ | `{policy_id, version, result}` — FK → `guardrail_span.csv` |
| `authority` | json | ✅ | `{approval_required, approval_status, approver_id}` — FK → `tool_span.csv` |
| `tool_action` | json | ⚪ | `{tool, result}` if the decision drove a tool call |
| `business_outcome` | json | ✅ | `{outcome, amount?}` — FK → `workflow_trace.outcome` |
| `owner` | string | ✅ | accountable function (maps to the accountability-layers table) |
| `risk_tier` | enum | ✅ | inherited from workflow |

**Mandatory-field rule:** a row missing any ✅ field is a *contract violation* and should be flagged by the generator/collector — mirroring how `otel-collector-config.yaml` rejects spans missing governance resource attributes.

---

## 4. Decision lifecycle (event model)

A decision is not a single instant; model it as a small state machine so override/bypass is provable:

```
proposed  →  policy_evaluated  →  [approval_pending]  →  authorised | overridden | blocked  →  executed  →  outcome_recorded
```

Each transition is an attribute update on the same `decision_id`, correlated to the guardrail/tool/human spans that caused it. The `guardrail_override` decision type exists precisely to make the `overridden` path first-class evidence rather than an inference.

---

## 5. Governance rules (the guardrails on the guardrail)

These are the non-negotiables the workshop must ratify **before** any real content is captured. Three of them are where this capability goes wrong if rushed.

1. **Structured rationale, never raw chain-of-thought.** `selection_basis` is a short, externally-inspectable list of grounded reasons (e.g. `damaged_item_confirmed`, `within_30_day_window`). It is **not** a dump of the model's internal reasoning tokens. Capturing hidden chain-of-thought is out of scope on privacy, security, and reliability grounds — consistent with the review's Table 7 boundary.

2. **Do not fabricate rationale or confidence.** ⚠️ *This is the sharpest risk.* In the mock, `selection_basis` and `confidence` are illustrative synthetic values and must be labelled as such in the UI. In production, they must be **actually emitted by the agent/orchestrator or a dedicated rationale-summariser** — never back-filled by the observability layer to look complete. A manufactured rationale is an overclaim, and it is the exact failure mode the rest of this repo's caveats culture exists to prevent. If the agent does not emit confidence, the field stays null; it is not invented.

3. **Redaction, retention, access by risk tier.** `input_facts` and `evidence_refs` may reference customer data. Apply the same rule as prompt/output logging (`roadmap.md` caveats): classify, hash/redact, and set a retention class *by risk tier* before logging real content. Decision records for `high` risk tiers get longer retention and tighter access than `low`.

4. **Observability ≠ authority.** The decision record is *evidence that controls operated*; it does not implement policy. Policy ownership stays with security / governance / risk / product (`datadog-mapping.md` positioning).

---

## 6. How it lights up existing surfaces

Nothing here is a parallel stack — it correlates into what exists.

| Surface | Change |
|---|---|
| **OTel** (`otel-conformance-matrix.md`) | new `decision` span, `gen_ai.demo.decision.*` attributes, parented to the workflow root span — sits alongside `workflow / llm / retrieval / tool / guardrail` |
| **Datadog** (`datadog-mapping.md`) | new facets for `decision_type, selected_action, policy_result, owner, risk_tier`; the `high-risk-action-without-approval` monitor becomes decision-scoped |
| **Metric wiring** | *Explainability coverage* (already in the catalogue as a target metric) becomes computable for real = % of consequential decisions with a complete `selection_basis` + `evidence_refs` |
| **Dashboard** | new **Decision Trace** view / decision-details panel (see backlog) |

---

## 7. Prioritised demonstrator backlog

Adopted from the review's P0/P1/P2, annotated with the §1 re-framing (much of the underlying data already exists, so P0 is mostly correlation + UI, not capture).

| Priority | Enhancement | What it delivers | Underlying data status |
|---|---|---|---|
| **P0** | `decision_span.csv` generator + OTLP decision span | the object itself, correlated by `workflow_id` | new; but reuses existing span rows as evidence |
| **P0** | Decision-details panel on the trace view | makes the decision inspectable as a first-class object | UI change |
| **P0** | Evidence + policy timeline in the panel | shows what informed and constrained the action | **data mostly exists** (retrieval + guardrail spans) — needs correlation |
| **P0** | Authority / approval record in the panel | proves who/what authorised it | **data mostly exists** (`tool_span.approval_status`, `guardrail_span.reviewer_id`) |
| **P1** | Candidate-option comparison | explains selection from the permitted set | new fields (`options_evaluated`, `selection_basis`) |
| **P1** | Decision-to-outcome link | connects technical behaviour to business impact | correlation to `workflow_trace.outcome` |
| **P1** | Search by decision type / policy result / risk / owner | investigator navigation | facets |
| **P2** | Replay & version comparison | regression analysis + continuous assurance | future maturity; needs versioned actors |

**Sequencing:** this completes the **Weeks 7–10 "Govern"** phase in `roadmap.md` (currently 🟡 partial) rather than opening a new workstream — the cleanest narrative for the architecture / risk committee.

---

## 8. Open decisions for the workshop (60–90 min, one scenario)

Anchor on **`refund_eligibility`** and leave with answers to all of these:

1. **Scope** — which decision types (§2) are in for v1? Confirm or trim the four.
2. **Schema** — which fields are mandatory? Ratify the ✅ column in §3, especially `confidence` (keep, or drop until the agent truly emits it?).
3. **Rationale generation** — who/what produces `selection_basis` in production without collecting chain-of-thought? (§5.1 / §5.2)
4. **Correlation set** — which policy / evaluator / human / outcome events must every decision link to?
5. **Governance** — retention, redaction, and access-control classes by risk tier. (§5.3)
6. **Proof scenario** — is refund eligibility the best end-to-end demonstrator, or is `guardrail_override` more compelling for the risk audience?
7. **Success measures** — which metrics show improved investigation, governance, and business outcome? (Candidate: explainability coverage, mean-time-to-reconstruct-a-decision, % decisions with proven authority.)

**Exit artefacts:** agreed event schema (this doc, ratified) · one UI wireframe · named owners per accountability layer · the P0 backlog above, committed.

---

*Once §8 is signed off, step 2 (build) is: generator → `decision_span.csv`, OTLP decision span, dashboard Decision Trace panel, Datadog decision dashboard + facets, and updates to `roadmap.md`, `metrics-catalogue.md`, and `otel-conformance-matrix.md`.*
