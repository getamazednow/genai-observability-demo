#!/usr/bin/env python3
"""
OTLP-JSON → contract-CSV bridge.

Reads the Collector file exporter's JSONL output (data/live/otlp_spans.jsonl)
and writes the SAME seven CSV schemas the synthetic generator produces — into
data/live/raw/, NEVER into data/synthetic/raw/. The existing aggregator and
dashboard then run unchanged:

    python ingest/bridge/otlp_file_to_csv.py
    GENAI_RAW_DIR=data/live/raw GENAI_OUT_DIR=dashboard/data \
        python data/generator/aggregate_dashboard_summary.py

This file is a conformance proof, not a product: if spans from all three cloud
emitters flow through the Collector and this bridge and the dashboard renders,
the telemetry contract holds. Production aggregation belongs to Datadog.

Mapping reference: docs/otel-conformance-matrix.md
Stdlib only, like the rest of the repo.
"""
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
IN_PATH = os.environ.get("GENAI_OTLP_JSONL", os.path.join(REPO, "data", "live", "otlp_spans.jsonl"))
OUT_DIR = os.environ.get("GENAI_RAW_DIR", os.path.join(REPO, "data", "live", "raw"))

HEADERS = {
    "workflow_trace.csv": "workflow_id,ml_app,service,env,version,use_case,business_unit,tenant,channel,risk_tier,user_hash,session_id,start_ts,outcome,total_latency_ms,total_cost_usd,llm_cost_usd,tool_cost_usd,retrieval_cost_usd,llm_call_count,tool_call_count,step_count,loop_count",
    "llm_span.csv": "workflow_id,ts,provider,model,model_version,operation,prompt_version,temperature,input_tokens,output_tokens,total_tokens,cost_usd,latency_ms,status,finish_reason",
    "retrieval_span.csv": "workflow_id,ts,retriever,index,query_type,top_k,source_ids,source_authority,source_freshness_days,retrieval_latency_ms,relevance_score,retrieval_cost_usd,retrieval_hit,groundedness_score,citation_accuracy_score,hallucination_flag,abstention_flag",
    "tool_span.csv": "workflow_id,ts,tool_name,tool_version,action_type,read_or_write,risk_class,approval_required,approval_status,latency_ms,status,error_type,cost_usd",
    "guardrail_span.csv": "workflow_id,ts,policy_name,policy_version,evaluator,score,threshold,allow_block_escalate,reason_code,reviewer_id",
    "incident_event.csv": "incident_id,severity,detected_ts,resolved_ts,affected_workflows,affected_users,root_cause_category,linked_trace_ids,detection_source,mitigation,recurrence_flag",
    "release_event.csv": "event_id,event_type,ts,artefact,from_version,to_version,golden_set_accuracy_pct,regression_test_pass_rate_pct,canary_health,notes",
}


def attr_value(v):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            val = v[k]
            return val if k != "intValue" else int(val)
    if "arrayValue" in v:
        vals = [attr_value(x) for x in v["arrayValue"].get("values", [])]
        return vals[0] if vals else ""
    return ""


def attrs_of(obj):
    return {a["key"]: attr_value(a["value"]) for a in obj.get("attributes", [])}


def iso(ns):
    return datetime.fromtimestamp(int(ns) / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dur_ms(span):
    return round((int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1e6)


def status_of(span, a):
    code = span.get("status", {}).get("code", 0)
    if code == 2 or a.get("error.type"):
        return "rate_limited" if str(a.get("error.type", "")) == "429" else "error"
    return "success"


def main():
    if not os.path.exists(IN_PATH):
        sys.exit(f"input not found: {IN_PATH} — run the Collector + an emitter first")
    os.makedirs(OUT_DIR, exist_ok=True)

    spans_by_trace = defaultdict(list)   # trace_id -> [(resource_attrs, span)]
    with open(IN_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            for rs in json.loads(line).get("resourceSpans", []):
                res = attrs_of(rs.get("resource", {}))
                for ss in rs.get("scopeSpans", []):
                    for span in ss.get("spans", []):
                        spans_by_trace[span["traceId"]].append((res, span))

    rows = {name: [] for name in HEADERS}
    for trace_id, items in spans_by_trace.items():
        root, res = None, {}
        children = defaultdict(list)  # op -> [(attrs, span)]
        for r, span in items:
            a = attrs_of(span)
            op = a.get("gen_ai.operation.name", "")
            if not span.get("parentSpanId"):
                root, res, root_attrs = span, r, a
            elif op in ("chat", "generate_content"):
                children["llm"].append((a, span))
            elif op == "execute_tool":
                children["tool"].append((a, span))
            elif op == "retrieve":
                children["retrieval"].append((a, span))
            elif op == "guardrail":
                children["guardrail"].append((a, span))
        if root is None:
            continue

        g = lambda d, k, default="": d.get(k, default)
        llm_cost = sum(float(g(a, "gen_ai.demo.cost_usd", 0)) for a, _ in children["llm"])
        tool_cost = sum(float(g(a, "gen_ai.demo.cost_usd", 0)) for a, _ in children["tool"])
        ret_cost = sum(float(g(a, "gen_ai.demo.cost_usd", 0)) for a, _ in children["retrieval"])
        step_count = sum(len(v) for v in children.values())

        rows["workflow_trace.csv"].append([
            trace_id, g(res, "gen_ai.demo.ml_app"), g(res, "service.name"),
            g(res, "deployment.environment.name"), g(res, "service.version"),
            g(res, "gen_ai.demo.use_case"), g(res, "gen_ai.demo.business_unit"),
            g(res, "gen_ai.demo.tenant"), g(res, "gen_ai.demo.channel"),
            g(res, "gen_ai.demo.risk_tier"), g(root_attrs, "gen_ai.demo.user_hash"),
            g(root_attrs, "gen_ai.conversation.id"), iso(root["startTimeUnixNano"]),
            g(root_attrs, "gen_ai.demo.outcome", "resolved"), dur_ms(root),
            round(llm_cost + tool_cost + ret_cost, 6), round(llm_cost, 6),
            round(tool_cost, 6), round(ret_cost, 6),
            len(children["llm"]), len(children["tool"]), step_count,
            int(g(root_attrs, "gen_ai.demo.loop_count", 0)),
        ])
        for a, s in children["llm"]:
            it, ot = int(g(a, "gen_ai.usage.input_tokens", 0)), int(g(a, "gen_ai.usage.output_tokens", 0))
            rows["llm_span.csv"].append([
                trace_id, iso(s["startTimeUnixNano"]), g(a, "gen_ai.provider.name"),
                g(a, "gen_ai.request.model"), g(a, "gen_ai.response.model"),
                g(a, "gen_ai.operation.name"), g(a, "gen_ai.demo.prompt_version"),
                g(a, "gen_ai.request.temperature", 0), it, ot, it + ot,
                g(a, "gen_ai.demo.cost_usd", 0), dur_ms(s), status_of(s, a),
                g(a, "gen_ai.response.finish_reasons", "stop"),
            ])
        for a, s in children["retrieval"]:
            p = "gen_ai.demo.retrieval."
            rows["retrieval_span.csv"].append([
                trace_id, iso(s["startTimeUnixNano"]), g(a, p + "retriever"), g(a, p + "index"),
                g(a, p + "query_type"), g(a, p + "top_k", 0), g(a, p + "source_ids"),
                g(a, p + "source_authority"), g(a, p + "source_freshness_days", 0),
                dur_ms(s), g(a, p + "relevance_score", 0), g(a, "gen_ai.demo.cost_usd", 0),
                str(bool(g(a, p + "retrieval_hit", False))),
                "", "", "", "",  # eval-harness columns: scheduled eval pipeline, not request spans
            ])
        for a, s in children["tool"]:
            p = "gen_ai.demo.tool."
            rows["tool_span.csv"].append([
                trace_id, iso(s["startTimeUnixNano"]), g(a, "gen_ai.tool.name"),
                g(a, "gen_ai.demo.tool_version"), g(a, p + "action_type"),
                g(a, p + "read_or_write"), g(a, p + "risk_class"),
                str(bool(g(a, p + "approval_required", False))), g(a, p + "approval_status"),
                dur_ms(s), status_of(s, a), g(a, "error.type"), g(a, "gen_ai.demo.cost_usd", 0),
            ])
        for a, s in children["guardrail"]:
            p = "gen_ai.demo.guardrail."
            rows["guardrail_span.csv"].append([
                trace_id, iso(s["startTimeUnixNano"]), g(a, p + "policy_name"),
                g(a, p + "policy_version"), g(a, p + "evaluator"), g(a, p + "score", 0),
                g(a, p + "threshold", 0), g(a, p + "allow_block_escalate"),
                g(a, p + "reason_code"), g(a, p + "reviewer_id"),
            ])

    for name, header in HEADERS.items():
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header.split(","))
            w.writerows(rows[name])
        print(f"wrote {len(rows[name]):>4} rows -> {path}")
    # incident_event / release_event are events, not spans: header-only by design.


if __name__ == "__main__":
    main()
