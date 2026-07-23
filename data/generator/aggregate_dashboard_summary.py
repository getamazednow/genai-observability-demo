#!/usr/bin/env python3
"""
Aggregates raw span-level CSVs into the daily rollup JSON consumed by the
static dashboard (dashboard/data/dashboard_summary.<source>.json, where
<source> is GENAI_SOURCE: "synthetic" default, or "live" for bridge output).

This mirrors what a real Datadog dashboard query would return: pre-aggregated
metric series, not raw spans. Run this after generate_synthetic_data.py.
"""

import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict
from datetime import datetime

BASE = os.path.join(os.path.dirname(__file__), "..", "synthetic")
# GENAI_SOURCE names the data source and the output file (dashboard_summary.<source>.json).
# "synthetic" (default) reads data/synthetic/raw; "live" reads data/live/raw (the CSVs
# produced by ingest/bridge/otlp_file_to_csv.py). GENAI_RAW_DIR still overrides the input
# directory explicitly if set.
SOURCE = os.environ.get("GENAI_SOURCE", "synthetic")
_default_raw = os.path.join(os.path.dirname(__file__), "..", "live", "raw") if SOURCE == "live" else os.path.join(BASE, "raw")
RAW = os.environ.get("GENAI_RAW_DIR", _default_raw)
OUT = os.environ.get("GENAI_OUT_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "dashboard", "data"))
OUT_NAME = f"dashboard_summary.{SOURCE}.json"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
os.makedirs(OUT, exist_ok=True)


def load_enabled_scenarios():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return [s for s in cfg["scenarios"] if s.get("enabled", True)]


def read_csv(name):
    path = os.path.join(RAW, name)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def read_csv_optional(name):
    """Like read_csv but returns [] if the file is absent. Used for decision_span.csv,
    which the synthetic generator emits but the live-telemetry bridge does not yet
    (decision events are emitted by agents/orchestrators — see docs/decision-contract.md)."""
    path = os.path.join(RAW, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def day_key(ts_str):
    return ts_str[:10]


def pct(values, p):
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


workflows = read_csv("workflow_trace.csv")
llm_spans = read_csv("llm_span.csv")
retrieval_spans = read_csv("retrieval_span.csv")
tool_spans = read_csv("tool_span.csv")
guardrail_spans = read_csv("guardrail_span.csv")
decision_spans = read_csv_optional("decision_span.csv")
incidents = read_csv("incident_event.csv")
release_events = read_csv("release_event.csv")

# Cost & capacity assumptions (would be real config in a production implementation)
DAILY_LLM_CALL_QUOTA = 700
MONTHLY_COST_BUDGET_USD = 150.0
PRIMARY_MODEL = "gpt-4o-mini"
FALLBACK_MODEL = "claude-3-5-haiku"

days = sorted(set(day_key(w["start_ts"]) for w in workflows))

by_day_wf = defaultdict(list)
for w in workflows:
    by_day_wf[day_key(w["start_ts"])].append(w)

by_day_llm = defaultdict(list)
for r in llm_spans:
    by_day_llm[day_key(r["ts"])].append(r)

by_day_tool = defaultdict(list)
for r in tool_spans:
    by_day_tool[day_key(r["ts"])].append(r)

by_day_retrieval = defaultdict(list)
for r in retrieval_spans:
    by_day_retrieval[day_key(r["ts"])].append(r)

by_day_guardrail = defaultdict(list)
for r in guardrail_spans:
    by_day_guardrail[day_key(r["ts"])].append(r)

by_day_decision = defaultdict(list)
for r in decision_spans:
    by_day_decision[day_key(r["ts"])].append(r)

eval_rnd = random.Random(7)  # deterministic wobble for the synthetic eval-harness series
cumulative_cost = 0.0

daily = []
for day_idx, d in enumerate(days):
    wfs = by_day_wf[d]
    llms = by_day_llm[d]
    tools = by_day_tool[d]
    retrievals = by_day_retrieval[d]
    guardrails = by_day_guardrail[d]

    total = len(wfs)
    resolved = sum(1 for w in wfs if w["outcome"] == "resolved")
    failed = sum(1 for w in wfs if w["outcome"] == "failed")
    escalated = sum(1 for w in wfs if w["outcome"] == "escalated_human")
    blocked = sum(1 for w in wfs if w["outcome"] == "blocked_policy")
    success_rate = round(100 * (resolved + escalated) / total, 2) if total else 0

    costs = [float(w["total_cost_usd"]) for w in wfs]
    total_cost = round(sum(costs), 2)
    llm_cost = round(sum(float(w.get("llm_cost_usd", 0)) for w in wfs), 2)
    tool_cost = round(sum(float(w.get("tool_cost_usd", 0)) for w in wfs), 2)
    retrieval_cost = round(sum(float(w.get("retrieval_cost_usd", 0)) for w in wfs), 2)
    successful_wfs = [w for w in wfs if w["outcome"] in ("resolved", "escalated_human")]
    cost_per_success = round(total_cost / len(successful_wfs), 4) if successful_wfs else 0

    latencies = [int(w["total_latency_ms"]) for w in wfs]
    p50 = round(pct(latencies, 0.50))
    p95 = round(pct(latencies, 0.95))
    p99 = round(pct(latencies, 0.99))

    llm_latencies = [int(r["latency_ms"]) for r in llms if r["status"] == "success"]
    model_p95 = round(pct(llm_latencies, 0.95)) if llm_latencies else 0
    retrieval_latencies = [int(r["retrieval_latency_ms"]) for r in retrievals]
    retrieval_p95 = round(pct(retrieval_latencies, 0.95)) if retrieval_latencies else 0
    tool_latencies = [int(r["latency_ms"]) for r in tools]
    tool_p95 = round(pct(tool_latencies, 0.95)) if tool_latencies else 0

    llm_errors = sum(1 for r in llms if r["status"] == "error")
    rate_limit_errors = sum(1 for r in llms if r.get("finish_reason") == "rate_limit_error")
    error_rate = round(100 * llm_errors / len(llms), 2) if llms else 0
    retry_rate = round(100 * sum(1 for w in wfs if int(w["llm_call_count"]) > 1) / total, 2) if total else 0
    tool_errors = sum(1 for r in tools if r["status"] == "error")
    tool_error_rate = round(100 * tool_errors / len(tools), 2) if tools else 0

    loop_events = sum(int(w["loop_count"]) for w in wfs)

    prompt_injection_attempts = sum(
        1 for g in guardrails if g["policy_name"] == "input_prompt_injection_scan"
        and g["allow_block_escalate"] in ("block", "bypass") or (g["reason_code"] == "prompt_injection_detected"))
    injection_blocked = sum(
        1 for g in guardrails if g["reason_code"] == "prompt_injection_detected" and g["allow_block_escalate"] == "block")
    injection_bypassed = sum(
        1 for g in guardrails if g["reason_code"] == "prompt_injection_detected" and g["allow_block_escalate"] == "allow")
    pii_egress = sum(1 for g in guardrails if g["reason_code"] == "pii_detected")
    toxicity_flags = sum(1 for g in guardrails if g["reason_code"] == "toxic_content")
    approval_bypasses = sum(1 for g in guardrails if g["reason_code"] == "approval_bypassed")

    high_risk_tool_calls = sum(1 for t in tools if t["risk_class"] == "high")

    by_tenant = defaultdict(int)
    for w in wfs:
        by_tenant[w["tenant"]] += 1

    by_usecase = defaultdict(int)
    for w in wfs:
        by_usecase[w["use_case"]] += 1

    # ---- AI Cost and Capacity ----
    input_tokens_total = sum(int(r["input_tokens"]) for r in llms)
    output_tokens_total = sum(int(r["output_tokens"]) for r in llms)
    cost_by_model = defaultdict(float)
    for r in llms:
        cost_by_model[r["model"]] += float(r["cost_usd"])
    cost_by_model = {k: round(v, 4) for k, v in cost_by_model.items()}
    fallback_cost_usd = round(cost_by_model.get(FALLBACK_MODEL, 0.0), 4)
    llm_call_count_day = len(llms)
    quota_utilization_pct = round(100 * llm_call_count_day / DAILY_LLM_CALL_QUOTA, 1)
    cumulative_cost += total_cost
    budget_burn_pct = round(100 * cumulative_cost / MONTHLY_COST_BUDGET_USD, 1)

    # ---- Agent Behaviour and Agency ----
    avg_step_count = round(statistics.mean(int(w["step_count"]) for w in wfs), 2) if wfs else 0
    avg_tool_calls_per_wf = round(statistics.mean(int(w["tool_call_count"]) for w in wfs), 2) if wfs else 0
    tool_calls_by_name = defaultdict(int)
    for t in tools:
        tool_calls_by_name[t["tool_name"]] += 1
    escalation_rate_pct = round(100 * escalated / total, 2) if total else 0
    tool_selection_success_pct = round(100 - tool_error_rate, 2)  # proxy: tool call succeeded

    # ---- RAG and Grounding Quality ----
    n_retrievals = len(retrievals)
    retrieval_hits = sum(1 for r in retrievals if r.get("retrieval_hit") in ("True", "true", True))
    retrieval_hit_rate_pct = round(100 * retrieval_hits / n_retrievals, 2) if n_retrievals else 0
    # Eval-harness columns may be empty when the CSVs come from the live-telemetry
    # bridge (ingest/bridge/): request spans never carry eval scores — a scheduled
    # eval pipeline does (see docs/otel-conformance-matrix.md). Treat empty as absent.
    _groundedness_vals = [float(r["groundedness_score"]) for r in retrievals if r.get("groundedness_score", "") != ""]
    _citation_vals = [float(r["citation_accuracy_score"]) for r in retrievals if r.get("citation_accuracy_score", "") != ""]
    avg_groundedness = round(statistics.mean(_groundedness_vals), 3) if _groundedness_vals else 0
    avg_citation_accuracy = round(statistics.mean(_citation_vals), 3) if _citation_vals else 0
    hallucination_count = sum(1 for r in retrievals if r.get("hallucination_flag") in ("True", "true", True))
    hallucination_rate_pct = round(100 * hallucination_count / n_retrievals, 2) if n_retrievals else 0
    abstention_count = sum(1 for r in retrievals if r.get("abstention_flag") in ("True", "true", True))
    abstention_rate_pct = round(100 * abstention_count / n_retrievals, 2) if n_retrievals else 0
    avg_source_freshness = round(statistics.mean(int(r["source_freshness_days"]) for r in retrievals), 1) if retrievals else 0

    # ---- AI Release and Evaluation (synthetic evaluation-harness series, sampled daily —
    # this does NOT derive from production spans, matching how a real eval pipeline runs
    # separately from live traffic). Dips around the seeded v14->v15 release/rollback window.
    dip = math.exp(-((day_idx - 8) ** 2) / 2.4)
    regression_pass_rate_pct = round(min(99.5, max(70, 97.6 - dip * 17 + eval_rnd.uniform(-0.8, 0.8))), 1)
    golden_set_accuracy_pct = round(min(97.0, max(65, 90.8 - dip * 12.5 + eval_rnd.uniform(-0.9, 0.9))), 1)
    active_prompt_version = "v15" if day_idx in (7, 8) else "v14"
    canary_health = "degraded" if day_idx == 7 else ("recovering" if day_idx == 8 else "healthy")

    # ---- Decision tracing (first-class decision records; see docs/decision-contract.md) ----
    decs = by_day_decision[d]
    decisions_total = len(decs)
    decision_overrides = sum(1 for x in decs if x["decision_type"] == "guardrail_override")
    decision_escalations = sum(1 for x in decs if x["selected_action"] in ("escalate_for_manual_review", "request_human_approval"))

    daily.append(dict(
        date=d,
        workflows_total=total,
        workflows_resolved=resolved,
        workflows_failed=failed,
        workflows_escalated=escalated,
        workflows_blocked_policy=blocked,
        success_rate_pct=success_rate,
        total_cost_usd=total_cost,
        llm_cost_usd=llm_cost,
        tool_cost_usd=tool_cost,
        retrieval_cost_usd=retrieval_cost,
        cost_per_successful_workflow_usd=cost_per_success,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_p99_ms=p99,
        model_latency_p95_ms=model_p95,
        retrieval_latency_p95_ms=retrieval_p95,
        tool_latency_p95_ms=tool_p95,
        llm_error_rate_pct=error_rate,
        rate_limit_events=rate_limit_errors,
        retry_rate_pct=retry_rate,
        tool_error_rate_pct=tool_error_rate,
        loop_events=loop_events,
        prompt_injection_attempts=prompt_injection_attempts,
        prompt_injection_blocked=injection_blocked,
        prompt_injection_bypassed=injection_bypassed,
        sensitive_data_egress_events=pii_egress,
        toxicity_flags=toxicity_flags,
        policy_approval_bypasses=approval_bypasses,
        high_risk_tool_calls=high_risk_tool_calls,
        workflows_by_tenant=dict(by_tenant),
        workflows_by_use_case=dict(by_usecase),

        # Cost & Capacity
        input_tokens_total=input_tokens_total,
        output_tokens_total=output_tokens_total,
        cost_by_model_usd=cost_by_model,
        fallback_cost_usd=fallback_cost_usd,
        llm_call_count=llm_call_count_day,
        quota_utilization_pct=quota_utilization_pct,
        daily_llm_call_quota=DAILY_LLM_CALL_QUOTA,
        cumulative_cost_usd=round(cumulative_cost, 2),
        budget_burn_pct=budget_burn_pct,

        # Agent Behaviour and Agency
        avg_step_count=avg_step_count,
        avg_tool_calls_per_workflow=avg_tool_calls_per_wf,
        tool_calls_by_name=dict(tool_calls_by_name),
        escalation_rate_pct=escalation_rate_pct,
        tool_selection_success_pct=tool_selection_success_pct,

        # RAG and Grounding Quality
        retrieval_hit_rate_pct=retrieval_hit_rate_pct,
        avg_groundedness_score=avg_groundedness,
        avg_citation_accuracy_score=avg_citation_accuracy,
        hallucination_rate_pct=hallucination_rate_pct,
        abstention_rate_pct=abstention_rate_pct,
        avg_source_freshness_days=avg_source_freshness,

        # AI Release and Evaluation
        regression_pass_rate_pct=regression_pass_rate_pct,
        golden_set_accuracy_pct=golden_set_accuracy_pct,
        active_prompt_version=active_prompt_version,
        canary_health=canary_health,

        # Decision tracing
        decisions_total=decisions_total,
        decision_overrides=decision_overrides,
        decision_escalations=decision_escalations,
    ))

# Overall / headline stats (last 30 days)
total_wf = len(workflows)
total_cost_all = round(sum(float(w["total_cost_usd"]) for w in workflows), 2)
successful_all = [w for w in workflows if w["outcome"] in ("resolved", "escalated_human")]
overall_success_rate = round(100 * len(successful_all) / total_wf, 2) if total_wf else 0
overall_cost_per_success = round(total_cost_all / len(successful_all), 4) if successful_all else 0
all_latencies = [int(w["total_latency_ms"]) for w in workflows]

enabled_scenarios = load_enabled_scenarios()
all_tenants = []
for s in enabled_scenarios:
    for t in s["tenants"]:
        if t not in all_tenants:
            all_tenants.append(t)
use_case_labels = [s.get("use_case_label", s["use_case"]) for s in enabled_scenarios]
business_units = sorted(set(s["business_unit"] for s in enabled_scenarios))
ml_apps = sorted(set(s["ml_app"] for s in enabled_scenarios))

# ---- Decision-tracing rollup (docs/decision-contract.md) ----
def _loads(s, default):
    try:
        return json.loads(s) if s else default
    except (json.JSONDecodeError, TypeError):
        return default

def parse_decision(x):
    return dict(
        decision_id=x["decision_id"], workflow_id=x["workflow_id"], ts=x["ts"],
        decision_type=x["decision_type"], actor_name=x["actor_name"], actor_version=x["actor_version"],
        objective=x["objective"], input_facts=_loads(x.get("input_facts"), {}),
        evidence_refs=_loads(x.get("evidence_refs"), []),
        evidence_freshness_days=x.get("evidence_freshness_days", ""),
        groundedness_score=float(x["groundedness_score"]) if x.get("groundedness_score") else None,
        options_evaluated=_loads(x.get("options_evaluated"), []),
        selected_action=x["selected_action"], selection_basis=_loads(x.get("selection_basis"), []),
        confidence=float(x["confidence"]) if x.get("confidence") else None,
        policy_evaluations=_loads(x.get("policy_evaluations"), []),
        authority=_loads(x.get("authority"), {}),
        tool_action=_loads(x.get("tool_action"), {}),
        business_outcome=_loads(x.get("business_outcome"), {}),
        owner=x.get("owner", ""), risk_tier=x.get("risk_tier", ""),
    )

total_decisions = len(decision_spans)
dec_by_type = defaultdict(int)
dec_by_action = defaultdict(int)
explainable = 0          # has a non-empty selection_basis AND evidence_refs
authority_proven = 0     # required-and-approved, or not required
for x in decision_spans:
    dec_by_type[x["decision_type"]] += 1
    dec_by_action[x["selected_action"]] += 1
    if _loads(x.get("selection_basis"), []) and _loads(x.get("evidence_refs"), []):
        explainable += 1
    auth = _loads(x.get("authority"), {})
    if (not auth.get("approval_required")) or (auth.get("approver_id")):
        authority_proven += 1

override_count = dec_by_type.get("guardrail_override", 0)
# Balanced, ts-sorted sample set for the details panel + searchable table (kept small for a static file).
_per_type_cap = {"refund_eligibility": 14, "high_risk_tool_invocation": 14, "escalation_vs_autoresolve": 10, "guardrail_override": 12}
_taken = defaultdict(int)
_samples_raw = []
for x in sorted(decision_spans, key=lambda r: r["ts"]):
    t = x["decision_type"]
    if _taken[t] < _per_type_cap.get(t, 10):
        _samples_raw.append(parse_decision(x))
        _taken[t] += 1
decision_samples = sorted(_samples_raw, key=lambda r: r["ts"])

decisions_summary = dict(
    total=total_decisions,
    explainability_coverage_pct=round(100 * explainable / total_decisions, 1) if total_decisions else 0,
    authority_coverage_pct=round(100 * authority_proven / total_decisions, 1) if total_decisions else 0,
    override_count=override_count,
    by_type=dict(dec_by_type),
    by_action=dict(dec_by_action),
    samples=decision_samples,
)

summary = dict(
    generated_at=datetime.utcnow().isoformat() + "Z",
    scenario=dict(
        # Backward-compatible single-string fields (used by the current dashboard UI):
        # join across scenarios so the KPI subtitle stays readable if more than one is enabled.
        use_case=" + ".join(use_case_labels),
        business_unit=" + ".join(business_units),
        ml_app=" + ".join(ml_apps),
        tenants=all_tenants,
        window_days=len(days),
        window_start=days[0] if days else None,
        window_end=days[-1] if days else None,
        # Full per-scenario breakdown for future dashboard use (e.g. a use-case filter).
        use_cases=[
            dict(id=s["id"], use_case=s["use_case"], use_case_label=s.get("use_case_label", s["use_case"]),
                 business_unit=s["business_unit"], ml_app=s["ml_app"], tenants=s["tenants"])
            for s in enabled_scenarios
        ],
    ),
    headline=dict(
        total_workflows=total_wf,
        overall_success_rate_pct=overall_success_rate,
        overall_cost_per_successful_workflow_usd=overall_cost_per_success,
        overall_total_cost_usd=total_cost_all,
        overall_latency_p95_ms=round(pct(all_latencies, 0.95)),
        incident_count=len(incidents),
        forecasted_monthly_runrate_usd=round(total_cost_all * (30 / max(len(days), 1)), 2),
        # Illustrative ROI framing for executive audiences: assumed fully-loaded cost of a
        # human-handled equivalent contact (industry rule-of-thumb range $4-$9; midpoint used).
        # This is a modelling assumption for the demo, not a sourced benchmark.
        assumed_human_handled_cost_usd=6.50,
        estimated_cost_avoidance_usd=round(len(successful_all) * 6.50 - total_cost_all, 2),
        monthly_cost_budget_usd=MONTHLY_COST_BUDGET_USD,
        daily_llm_call_quota=DAILY_LLM_CALL_QUOTA,
        rollback_count=sum(1 for r in release_events if r["event_type"] == "rollback"),
    ),
    daily=daily,
    incidents=incidents,
    release_events=release_events,
    decisions=decisions_summary,
)

summary["source"] = SOURCE

with open(os.path.join(OUT, OUT_NAME), "w") as f:
    json.dump(summary, f, indent=2)

# Legacy filename kept in sync for the synthetic default so older links/docs still work.
if SOURCE == "synthetic":
    with open(os.path.join(OUT, "dashboard_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

print(f"Wrote {OUT_NAME} with {len(daily)} days, {total_wf} workflows, {len(incidents)} incidents.")
