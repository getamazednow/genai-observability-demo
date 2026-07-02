# Training

Training and enablement material for the GenAI Project Observability demo — built to support architecture-board reviews, risk-committee walkthroughs and Community of Practice (CoP) sessions. Everything here explains the demo in `../dashboard`, `../data` and `../datadog`; it does not add new functionality to the demo itself.

## What's in this folder

```
training/
├── README.md                          — this file
├── reading/                            — deep-dive narrative, one topic per file
│   ├── 01-demo-overview.md             — what the demo is, why it exists, the scenario, headline numbers
│   ├── 02-dashboard-user-guide.md      — how to run and read all 7 dashboard tabs
│   ├── 03-architecture-and-caveats.md  — architecture choices, known gaps, caveats to carry forward
│   ├── 04-roadmap-and-next-steps.md    — the 90-day roadmap, annotated, plus build requirements/dependencies
│   ├── 05-datadog-implementation-reference.md — Datadog APIs, monitors, SLOs, connectors, metric namespace
│   └── 06-claude-code-production-build-plan.md — a phased, gated plan for an agent to build the real infrastructure
├── diagrams/
│   ├── mermaid/                        — GitHub-native diagram source (*.mmd)
│   ├── exports/                        — high-res PNG renders of the same 6 diagrams, for slides/docs
│   └── README.md                       — all 6 diagrams rendered inline
├── docx/
│   └── GenAI-Observability-Training-Guide.docx — consolidated Word version of reading/, with diagrams embedded
└── slides/
    ├── GenAI-Observability-Exec-Overview.pptx        — points 1–4: what/how/why/roadmap (board & CoP audience)
    └── GenAI-Observability-Technical-Deepdive.pptx   — points 5–7: build requirements, Datadog reference, agent build plan
```

## Suggested use by audience

| Audience | Start here |
|---|---|
| Architecture board / risk committee / executive CoP | `slides/GenAI-Observability-Exec-Overview.pptx`, then `reading/01-demo-overview.md` and `reading/03-architecture-and-caveats.md` |
| Platform engineering / SRE about to run the demo | `reading/02-dashboard-user-guide.md` |
| Engineers scoping the real Datadog build | `slides/GenAI-Observability-Technical-Deepdive.pptx`, then `reading/05-datadog-implementation-reference.md` and `reading/06-claude-code-production-build-plan.md` |
| Anyone wanting one offline document | `docx/GenAI-Observability-Training-Guide.docx` |

## Facilitator notes for a live CoP session (suggested ~45 minute agenda)

1. **(5 min) Frame the problem** — why conventional APM misses agentic-AI failure modes (`reading/01-demo-overview.md`, "Why conventional APM isn't enough").
2. **(10 min) Live dashboard walkthrough** — follow the suggested order in `reading/02-dashboard-user-guide.md`: Executive Health → Security incident spotlight → Engineering trace waterfall → Cost & Capacity.
3. **(10 min) Be explicit about what's real vs. mocked** — `reading/03-architecture-and-caveats.md`, especially the synthetic evaluation-harness caveat. This is the section most likely to be challenged by a technically sophisticated audience; presenting it up front builds credibility rather than losing it.
4. **(10 min) Roadmap and what it takes to go live** — `reading/04-roadmap-and-next-steps.md` plus the roadmap timeline diagram.
5. **(10 min) Q&A**, using `reading/05-datadog-implementation-reference.md` and `reading/06-claude-code-production-build-plan.md` as backup material for technical questions on implementation.

## Keeping this material in sync

This folder documents `../dashboard`, `../data`, `../datadog` and the two source PDFs — it does not own any of that logic. If the dashboard tabs, synthetic data schema, or Datadog templates change, treat `reading/02-dashboard-user-guide.md` and `reading/05-datadog-implementation-reference.md` as needing a review pass, and re-export any diagram whose underlying facts changed (see `diagrams/README.md` for the mermaid/PNG pairing convention).
