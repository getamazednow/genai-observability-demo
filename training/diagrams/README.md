# Architecture diagrams

Six diagrams supporting the training material, in two forms:

- **`mermaid/*.mmd`** — GitHub-native source. Rendered automatically below and directly on GitHub wherever these files are linked or embedded in a fenced ` ```mermaid ` block.
- **`exports/*.png`** — high-resolution rasters of the same content, used in the two PowerPoint decks (`../slides/`) and the consolidated Word training guide (`../docx/`).

If you edit a diagram, update both: the `.mmd` source for GitHub/dev-facing use, and re-export a PNG for slide/doc use (no build tool wires these together automatically — treat them as a matched pair to keep in sync by hand).

## 1. Observability trace-tree architecture

Every workflow is one connected trace, not isolated logs — the architectural principle underpinning every dashboard in this repo.

```mermaid
flowchart TD
    A["User Request<br/><small>workflow_id . use_case . tenant . channel . risk_tier</small>"]
    B["Policy / Guardrail Check<br/><small>policy_name . evaluator . allow / block / escalate</small>"]
    C["Context Assembly<br/><small>session state . user profile . conversation history</small>"]
    D["Retrieval<br/><small>retriever . top_k . source_authority . relevance_score</small>"]
    E["Planning<br/><small>step decomposition . tool selection</small>"]
    F["Model Call(s)<br/><small>provider . model . tokens . cost . latency . finish_reason</small>"]
    G["Tool Call(s)<br/><small>tool_name . risk_class . approval_required . read/write</small>"]
    H["Evaluator / Guardrail Check<br/><small>groundedness . citation accuracy . toxicity</small>"]
    I{"Human Approval<br/>required?"}
    J["Final Outcome<br/><small>resolved . escalated_human . blocked_policy . failed</small>"]

    A --> B --> C --> D --> E --> F --> G --> H --> I
    I -- yes --> K["Human reviewer approves / rejects"] --> J
    I -- no --> J

    classDef req fill:#0F3460,stroke:#16213E,color:#fff
    classDef guard fill:#1F9E97,stroke:#16213E,color:#fff
    classDef mid fill:#3E5C76,stroke:#16213E,color:#fff
    classDef human fill:#E0982A,stroke:#16213E,color:#fff
    classDef out fill:#16213E,stroke:#16213E,color:#fff

    class A req
    class B,H guard
    class C,D,E mid
    class F,G req
    class I,K human
    class J out
```

## 2. Demo data flow — synthetic telemetry pipeline (mock)

How this repo's mock pipeline is generated, and its real-implementation counterpart.

```mermaid
flowchart LR
    subgraph MOCK["THIS DEMO (mock)"]
        direction LR
        SRC["Source Documents<br/>Metrics Catalogue +<br/>Datadog Addendum PDFs"] --> GEN["Python Generator<br/>generate_synthetic_data.py"]
        GEN --> S1["workflow_trace.csv"]
        GEN --> S2["llm_span.csv"]
        GEN --> S3["retrieval_span.csv"]
        GEN --> S4["tool_span.csv"]
        GEN --> S5["guardrail_span.csv"]
        GEN --> S6["incident_event.csv"]
        GEN --> S7["release_event.csv"]
        S1 & S2 & S3 & S4 & S5 & S6 & S7 --> AGG["Aggregator<br/>aggregate_dashboard_summary.py"]
        AGG --> JSON["dashboard_summary.json"]
        JSON --> DASH["Static Dashboard<br/>index.html + app.js<br/>(7 tabs, Chart.js)"]
    end

    subgraph REAL["PRODUCTION (real) -- post mock-to-real"]
        direction LR
        LIVE["Live Agent/App<br/>+ Datadog LLM Obs SDK / OTel"] --> DD["Datadog Platform<br/>LLM Obs . APM . Logs . Metrics"]
        DD --> DAC["Dashboards-as-code<br/>datadog/*.json"]
        DAC --> NDD["Native Datadog<br/>Dashboards / Monitors / SLOs"]
    end

    classDef mockNode fill:#DCF2F0,stroke:#1F9E97,color:#16213E
    classDef genNode fill:#0F3460,stroke:#16213E,color:#fff
    classDef realNode fill:#F7DDDA,stroke:#C0392B,color:#16213E
    class S1,S2,S3,S4,S5,S6,S7 mockNode
    class GEN,AGG,DASH genNode
    class JSON mockNode
    class SRC mockNode
    class LIVE,DD,DAC,NDD realNode
```

## 3. Mock to real migration

What changes and what carries over unchanged, per `docs/datadog-mapping.md`.

```mermaid
flowchart LR
    subgraph M["THIS DEMO (mock)"]
        direction TB
        M1["1. Python generator scripts<br/>data/generator/*.py"]
        M2["2. aggregate_dashboard_summary.py<br/>local rollup logic"]
        M3["3. Static dashboard/ app<br/>reads local JSON"]
        M4["4. Monitor / SLO JSON<br/>definitions only, not wired"]
        M5["5. Synthetic eval-harness series<br/>groundedness, hallucination, etc."]
    end

    subgraph R["PRODUCTION (real)"]
        direction TB
        R1["Datadog LLM/Agent Obs SDK<br/>or OpenTelemetry GenAI semconv"]
        R2["Datadog dashboard widget<br/>queries (same aggregations)"]
        R3["Native Datadog dashboards<br/>from datadog/dashboards/*.json"]
        R4["Live monitors + SLOs wired to<br/>real on-call / PagerDuty / Slack"]
        R5["Real eval harness: LLM-as-judge +<br/>human review + golden sets"]
    end

    M1 --> R1
    M2 --> R2
    M3 --> R3
    M4 --> R4
    M5 --> R5

    classDef mockNode fill:#DCF2F0,stroke:#1F9E97,color:#16213E
    classDef realNode fill:#F7DDDA,stroke:#C0392B,color:#16213E
    class M1,M2,M3,M4,M5 mockNode
    class R1,R2,R3,R4,R5 realNode
```

## 4. 90-day roadmap timeline

```mermaid
timeline
    title 90-Day Path to Production Capability
    section Weeks 0-2 : Foundation -- DONE (mock)
        Telemetry contract : Tag taxonomy : Risk tiers : First pilot workflow
    section Weeks 3-6 : Operate -- DONE (mock)
        7 dashboards built : SLOs/monitors defined : 3 seeded incident stories
    section Weeks 7-10 : Govern -- PARTIAL
        Real eval harness (gap) : DLP / Sensitive Data Scanner (gap) : Human-review telemetry (partial)
    section Weeks 11-13 : Scale -- NOT STARTED
        Reusable instrumentation library : Onboarding checklist : Golden dashboards
```

## 5. Dashboard information architecture

```mermaid
flowchart TB
    T["Common Trace Tree<br/>workflow . llm . retrieval . tool . guardrail spans"]

    T --> D1["1. Executive AI Health<br/><i>C-suite / Board</i><br/>Volume, success rate, cost avoidance, P95, incidents"]
    T --> D2["2. Engineering Operations<br/><i>Platform Engineering</i><br/>Latency by layer, error/retry, rate limits, trace waterfall"]
    T --> D3["3. Security & Responsible AI<br/><i>CyberSec / Risk</i><br/>Injection attempts, egress, toxicity, approval bypass"]
    T --> D4["4. Cost & Capacity<br/><i>FinOps / Product Owner</i><br/>Tokens, cost by model, quota, budget burn"]
    T --> D5["5. Agent Behaviour<br/><i>AI/Agent Engineering</i><br/>Steps & tool-calls per workflow, escalation, tool mix"]
    T --> D6["6. RAG & Grounding<br/><i>Data / ML / Responsible AI</i><br/>Hit rate, groundedness, hallucination, abstention"]
    T --> D7["7. Release & Evaluation<br/><i>Release Eng / QA</i><br/>Regression pass rate, golden-set accuracy, rollback log"]

    classDef root fill:#16213E,stroke:#16213E,color:#fff
    classDef d fill:#0F3460,stroke:#16213E,color:#fff
    class T root
    class D1,D2,D3,D4,D5,D6,D7 d
```

## 6. Target Datadog implementation architecture

```mermaid
flowchart TB
    L1["INSTRUMENTATION<br/>Agent/App code . Datadog LLM & Agent Observability SDK . OpenTelemetry GenAI semantic conventions"]
    L2["INGESTION<br/>Datadog Agent . OTel Collector . API/Intake endpoints (traces, spans, logs, metrics)"]
    L3["DATADOG PLATFORM<br/>LLM Observability . APM . Log Management . Metrics . Sensitive Data Scanner . Managed/Custom Evaluations"]
    L4["CONSUMPTION<br/>Dashboards-as-code (datadog/dashboards) . Notebooks . Monitors (datadog/monitors) . SLOs (datadog/slos)"]
    L5["ACTION<br/>PagerDuty / Slack / ServiceNow on-call routing . Runbooks . Incident Management"]

    L1 --> L2 --> L3 --> L4 --> L5

    G["Governance overlay:<br/>policy ownership stays with<br/>Architecture / Security / Data Governance / Risk<br/>(Datadog operationalises, does not replace it)"]
    L1 -.-> G
    L2 -.-> G
    L3 -.-> G
    L4 -.-> G

    classDef inst fill:#0F3460,stroke:#16213E,color:#fff
    classDef ing fill:#3E5C76,stroke:#16213E,color:#fff
    classDef plat fill:#1F9E97,stroke:#16213E,color:#fff
    classDef cons fill:#E0982A,stroke:#16213E,color:#fff
    classDef act fill:#C0392B,stroke:#16213E,color:#fff
    classDef gov fill:#F6F7F9,stroke:#16213E,color:#16213E,stroke-dasharray: 4 3

    class L1 inst
    class L2 ing
    class L3 plat
    class L4 cons
    class L5 act
    class G gov
```
