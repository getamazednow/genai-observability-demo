# /ingest — tri-cloud OTel receiving scaffold

The receiving scaffold for real GenAI telemetry from **Azure AI Foundry**,
**Vertex AI / Gemini (ADK)** and **AWS Bedrock AgentCore** — all of which emit
OpenTelemetry GenAI spans natively. One Collector, two exporters:

```
Azure Foundry ─┐                                  ┌─> file/JSONL ─> bridge ─> data/live/raw/*.csv ─> existing aggregator ─> existing dashboard
Vertex/ADK ────┼─> OTLP ─> Collector (contract    │
Bedrock ───────┘           tags, redaction) ──────┴─> Datadog LLM Observability (env-gated)
```

The contract the Collector enforces is pinned in
[`docs/otel-conformance-matrix.md`](../docs/otel-conformance-matrix.md).
Platform metrics (quota/throttling/billing) intentionally bypass this pipeline —
they arrive via Datadog's native cloud integrations.

## Layout

| Path | Purpose |
|---|---|
| `collector/otel-collector-config.yaml` | The spine: OTLP in, contract-tag flagging, prompt-content stripping, dual export |
| `emitters/contract_emitter.py` | Shared span-tree builder conforming to the contract |
| `emitters/{azure_foundry,gcp_adk,aws_agentcore}_emitter.py` | Platform-flavoured samples — stand-ins for the real SDK emission |
| `bridge/otlp_file_to_csv.py` | Collector JSONL → the seven contract CSVs (`data/live/raw/`, never `data/synthetic/raw/`) |

## Run the demo path end-to-end

```bash
# 0. Once: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
#    and install otelcol-contrib (https://opentelemetry.io/docs/collector/installation/)

# 1. Collector (terminal 1)
cd ingest/collector && otelcol-contrib --config otel-collector-config.yaml

# 2. Emit one workflow per cloud (terminal 2)
cd ingest/emitters
python azure_foundry_emitter.py && python gcp_adk_emitter.py && python aws_agentcore_emitter.py

# 3. Bridge OTLP JSONL -> contract CSVs
python ingest/bridge/otlp_file_to_csv.py

# 4. Aggregate + view — the SAME aggregator and dashboard as the synthetic demo
GENAI_SOURCE=live python data/generator/aggregate_dashboard_summary.py   # writes dashboard/data/dashboard_summary.live.json
cd dashboard && python3 -m http.server 8000
# open http://localhost:8000 and flip the Synthetic|Live toggle in the top bar
```

No Collector handy? Every emitter takes `--console` to print its spans, and the
bridge accepts any file in Collector file-exporter format via `GENAI_OTLP_JSONL=...`.

## Design rules (why this can't break the demo)

- The bridge **writes to `data/live/raw/` only**; `data/synthetic/raw/` is never
  touched. Live aggregation writes its own `dashboard_summary.live.json` — the
  synthetic summary file is never overwritten, so the synthetic demo always works.
- `data/live/` is gitignored — live telemetry is runtime state, not repo content.
  (A sample `dashboard_summary.live.json` *is* committed so the dashboard's Live
  toggle works from a clean clone.)
- Prompt/output content is stripped in the Collector **by default**; logging
  content is a governance decision per risk tier, made deliberately.
- Contract-tag violations are flagged, not dropped, so conformance gaps show up
  on a dashboard instead of disappearing.

## Production note

This lane proves the contract; it is not the production pipeline. Production =
same emitters/Collector with the `datadog` exporter enabled (`DD_API_KEY`,
`DD_SITE`), dashboards from `datadog/dashboards/`, monitors/SLOs from
`datadog/monitors|slos/`. See `docs/roadmap.md` Weeks 0–2.
