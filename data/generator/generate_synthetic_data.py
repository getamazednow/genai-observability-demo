#!/usr/bin/env python3
"""
Synthetic telemetry generator for the GenAI Observability demo.

Scenario: "Order Support & Returns Assistant" — an agentic retail customer-
service workflow (order status, returns, refunds, loyalty credits) spanning
three storefront tenants (brand_a, brand_b, brand_c).

Output follows the telemetry contract defined in the companion source
documents (AI Observability Metrics Catalogue + Datadog Implementation
Addendum): a workflow trace plus five span types (llm, retrieval, tool,
guardrail/evaluation) and a small incident_event table.

Three deliberate storylines are seeded so the resulting dashboards show a
diagnosable signal rather than flat noise:
  1. A v14 -> v15 prompt release regression, caught and rolled back (days 8-9)
  2. Prompt-injection cluster targeting the refund tool (days 12-13)
  3. Provider rate-limit / cost-spike cascade from a promo traffic surge (days 21-22)

Usage:
    python3 generate_synthetic_data.py

Writes raw span-level CSVs to ../synthetic/raw/ and a pre-aggregated daily
rollup to ../synthetic/dashboard_summary.json (what the static dashboard
consumes — mirroring what a real Datadog dashboard query would return).
"""

import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "synthetic")
RAW_DIR = os.path.join(OUT_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)

DAYS = 30
END_DATE = datetime(2026, 6, 30, tzinfo=timezone.utc)
START_DATE = END_DATE - timedelta(days=DAYS - 1)

TENANTS = ["brand_a", "brand_b", "brand_c"]
CHANNELS = ["web_chat", "mobile_app", "ivr_handoff"]
USE_CASE = "order_support_returns_assistant"
BUSINESS_UNIT = "Retail Customer Care"
ML_APP = "retail-support-agent"
SERVICE = "support-agent-orchestrator"
ENV = "production"
VERSION = "2.4.1"

PRIMARY_PROVIDER, PRIMARY_MODEL = "openai", "gpt-4o-mini"
FALLBACK_PROVIDER, FALLBACK_MODEL = "anthropic", "claude-3-5-haiku"

RETRIEVERS = [("returns_policy_kb", "policy_lookup"), ("order_history_index", "order_lookup"),
              ("faq_kb", "faq_lookup")]

TOOLS = [
    dict(name="order_lookup", version="1.3.0", action_type="read", read_or_write="read", risk_class="low"),
    dict(name="shipping_status", version="1.1.0", action_type="read", read_or_write="read", risk_class="low"),
    dict(name="refund_issue", version="2.0.0", action_type="write", read_or_write="write", risk_class="high"),
    dict(name="loyalty_credit", version="1.4.0", action_type="write", read_or_write="write", risk_class="medium"),
    dict(name="address_update", version="1.0.2", action_type="write", read_or_write="write", risk_class="high"),
]

GUARDRAIL_POLICIES = [
    dict(name="input_prompt_injection_scan", version="3.1", evaluator="injection_classifier_v3"),
    dict(name="output_pii_egress_scan", version="2.2", evaluator="dlp_scanner_v2"),
    dict(name="output_toxicity_check", version="1.5", evaluator="toxicity_classifier_v1"),
    dict(name="high_risk_action_approval", version="1.0", evaluator="policy_engine"),
]

RISK_TIERS = ["low", "medium", "high"]


def daterange():
    for i in range(DAYS):
        yield START_DATE + timedelta(days=i)


def day_index(d):
    return (d - START_DATE).days


def is_promo_spike_day(d):
    # Rate-limit / cost-spike incident window
    return day_index(d) in (20, 21)


def is_injection_cluster_day(d):
    return day_index(d) in (11, 12)


def is_release_regression_window(d):
    # Prompt v14 -> v15 rollout, regression detected, rollback back to v14
    return day_index(d) in (7, 8)


def base_volume_for_day(d):
    idx = day_index(d)
    weekday = d.weekday()
    base = 140 + idx * 2  # slight upward trend over the month
    if weekday >= 5:  # weekend dip
        base = int(base * 0.7)
    if is_promo_spike_day(d):
        base = int(base * 2.3)  # promo traffic surge
    return base


workflow_rows = []
llm_rows = []
retrieval_rows = []
tool_rows = []
guardrail_rows = []
incident_rows = []

INCIDENT_TRACE_IDS = {"injection": [], "rate_limit": []}

for d in daterange():
    n_workflows = base_volume_for_day(d) + random.randint(-15, 15)
    injection_day = is_injection_cluster_day(d)
    spike_day = is_promo_spike_day(d)
    release_window = is_release_regression_window(d)
    active_prompt_version = "v15" if release_window else "v14"

    for _ in range(max(n_workflows, 1)):
        workflow_id = str(uuid.uuid4())
        ts = d + timedelta(seconds=random.randint(0, 86399))
        tenant = random.choice(TENANTS)
        channel = random.choices(CHANNELS, weights=[0.55, 0.35, 0.10])[0]
        session_id = str(uuid.uuid4())
        user_hash = uuid.uuid4().hex[:12]

        # ---- Guardrail: input scan ----
        is_injection_attempt = False
        if injection_day and random.random() < 0.18:
            is_injection_attempt = True
        elif random.random() < 0.008:
            is_injection_attempt = True  # low background rate

        input_block = False
        if is_injection_attempt:
            # Guardrail catches most; rare bypass -> incident
            caught = random.random() < 0.92
            input_block = caught
            guardrail_rows.append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), policy_name="input_prompt_injection_scan",
                policy_version="3.1", evaluator="injection_classifier_v3",
                score=round(random.uniform(0.82, 0.99), 3), threshold=0.75,
                allow_block_escalate=("block" if caught else "allow"),
                reason_code="prompt_injection_detected", reviewer_id=""
            ))
            if not caught:
                INCIDENT_TRACE_IDS["injection"].append(workflow_id)
        else:
            guardrail_rows.append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), policy_name="input_prompt_injection_scan",
                policy_version="3.1", evaluator="injection_classifier_v3",
                score=round(random.uniform(0.0, 0.15), 3), threshold=0.75,
                allow_block_escalate="allow", reason_code="", reviewer_id=""
            ))

        if input_block:
            # Workflow terminated at the guardrail — no LLM/tool spend incurred
            workflow_rows.append(dict(
                workflow_id=workflow_id, ml_app=ML_APP, service=SERVICE, env=ENV, version=VERSION,
                use_case=USE_CASE, business_unit=BUSINESS_UNIT, tenant=tenant, channel=channel,
                risk_tier="high", user_hash=user_hash, session_id=session_id,
                start_ts=ts.isoformat(), outcome="blocked_policy",
                total_latency_ms=random.randint(120, 300), total_cost_usd=0.0,
                llm_cost_usd=0.0, tool_cost_usd=0.0, retrieval_cost_usd=0.0,
                llm_call_count=0, tool_call_count=0, step_count=1, loop_count=0
            ))
            continue

        # ---- Rate limit / fallback dynamics (spike days) ----
        rate_limited = spike_day and random.random() < 0.30
        used_fallback = rate_limited and random.random() < 0.75

        # ---- Retrieval span ----
        retriever, query_type = random.choice(RETRIEVERS)
        retrieval_latency = max(30, int(random.gauss(180, 60)))
        if spike_day:
            retrieval_latency = int(retrieval_latency * 1.4)
        relevance = round(random.uniform(0.55, 0.98), 3)
        retrieval_cost = round(random.uniform(0.0003, 0.0009), 5)  # vector search + embedding cost

        # RAG/grounding quality signals. Groundedness and citation accuracy track retrieval
        # relevance under normal conditions; the v15 prompt regression window degrades both
        # independently of retrieval quality (the prompt change, not the retriever, is at fault) —
        # this is what a real groundedness-eval monitor would surface as the release regression.
        groundedness = relevance * random.uniform(0.88, 1.03)
        citation_accuracy = relevance * random.uniform(0.85, 1.05)
        if release_window:
            groundedness *= random.uniform(0.55, 0.72)
            citation_accuracy *= random.uniform(0.55, 0.75)
        groundedness = round(max(0.0, min(1.0, groundedness)), 3)
        citation_accuracy = round(max(0.0, min(1.0, citation_accuracy)), 3)
        retrieval_hit = relevance >= 0.62
        hallucination_flag = (groundedness < 0.55 and random.random() < 0.15) or random.random() < 0.004
        abstention_flag = (not hallucination_flag) and groundedness < 0.4 and random.random() < 0.30

        retrieval_rows.append(dict(
            workflow_id=workflow_id, ts=ts.isoformat(), retriever=retriever, index=retriever,
            query_type=query_type, top_k=5,
            source_ids=f"{retriever}:{random.randint(1000,9999)}", source_authority="approved",
            source_freshness_days=random.randint(0, 45),
            retrieval_latency_ms=retrieval_latency, relevance_score=relevance,
            retrieval_cost_usd=retrieval_cost, retrieval_hit=retrieval_hit,
            groundedness_score=groundedness, citation_accuracy_score=citation_accuracy,
            hallucination_flag=hallucination_flag, abstention_flag=abstention_flag
        ))

        # ---- LLM span(s): planner/generator call, occasionally a retry+fallback ----
        n_llm_calls = 1
        loop_count = 0
        if random.random() < 0.06:
            n_llm_calls += 1  # self-correction / replanning
            loop_count = 1
        if rate_limited:
            n_llm_calls += 1  # retry after rate-limit error

        total_cost = 0.0
        total_llm_latency = 0
        finish_status = "success"
        for call_i in range(n_llm_calls):
            provider, model = PRIMARY_PROVIDER, PRIMARY_MODEL
            status = "success"
            finish_reason = "stop"
            if rate_limited and call_i == 0:
                status = "error"
                finish_reason = "rate_limit_error"
            elif rate_limited and call_i == n_llm_calls - 1 and used_fallback:
                provider, model = FALLBACK_PROVIDER, FALLBACK_MODEL

            input_tokens = random.randint(350, 1400)
            output_tokens = random.randint(60, 420)
            latency = max(200, int(random.gauss(950, 300)))
            if spike_day:
                latency = int(latency * random.uniform(1.3, 2.2))
            if status == "error":
                latency = int(latency * 0.4)
                cost = 0.0
            else:
                # illustrative $/1K token pricing, primary cheaper than fallback
                rate_in, rate_out = (0.00015, 0.0006) if model == PRIMARY_MODEL else (0.0008, 0.0040)
                cost = round((input_tokens / 1000) * rate_in + (output_tokens / 1000) * rate_out, 5)

            total_cost += cost
            total_llm_latency += latency
            llm_rows.append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), provider=provider, model=model,
                model_version="2026-05", operation="chat.completions", prompt_version=active_prompt_version,
                temperature=0.2, input_tokens=input_tokens, output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens, cost_usd=cost, latency_ms=latency,
                status=status, finish_reason=finish_reason
            ))
            if status == "error":
                finish_status = "recovered_after_retry"

        # ---- Tool span(s) ----
        # Tool cost approximates external API/SaaS/gateway fees (e.g. payment gateway fee on a
        # refund) — this is the "tool-call cost" and "high-risk tool invocation" cost dimension
        # called out separately from model cost in the metrics catalogue.
        TOOL_COST_BY_RISK = dict(low=0.0015, medium=0.012, high=0.035)
        n_tools = random.choices([0, 1, 2, 3], weights=[0.10, 0.45, 0.35, 0.10])[0]
        tool_call_count = 0
        total_tool_latency = 0
        total_tool_cost = 0.0
        high_risk_without_approval = False
        for _ in range(n_tools):
            tool = random.choice(TOOLS)
            approval_required = tool["risk_class"] in ("medium", "high")
            approval_status = "n/a"
            if approval_required:
                approval_status = "approved" if random.random() < 0.97 else "auto_approved_no_review"
                if approval_status == "auto_approved_no_review" and tool["risk_class"] == "high":
                    high_risk_without_approval = True
            latency = max(80, int(random.gauss(320, 120)))
            status = "success" if random.random() < 0.96 else "error"
            error_type = "" if status == "success" else random.choice(
                ["timeout", "schema_validation_error", "downstream_5xx"])
            tool_cost = round(TOOL_COST_BY_RISK[tool["risk_class"]] * random.uniform(0.85, 1.15), 5) \
                if status == "success" else 0.0
            tool_rows.append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), tool_name=tool["name"],
                tool_version=tool["version"], action_type=tool["action_type"],
                read_or_write=tool["read_or_write"], risk_class=tool["risk_class"],
                approval_required=approval_required, approval_status=approval_status,
                latency_ms=latency, status=status, error_type=error_type, cost_usd=tool_cost
            ))
            total_tool_latency += latency
            total_tool_cost += tool_cost
            tool_call_count += 1

        # ---- Guardrail: output scan ----
        pii_egress = random.random() < 0.004
        toxicity_flag = random.random() < 0.002
        guardrail_rows.append(dict(
            workflow_id=workflow_id, ts=ts.isoformat(), policy_name="output_pii_egress_scan",
            policy_version="2.2", evaluator="dlp_scanner_v2",
            score=round(random.uniform(0.85, 0.99) if pii_egress else random.uniform(0.0, 0.2), 3),
            threshold=0.8, allow_block_escalate=("block" if pii_egress else "allow"),
            reason_code=("pii_detected" if pii_egress else ""), reviewer_id=""
        ))
        guardrail_rows.append(dict(
            workflow_id=workflow_id, ts=ts.isoformat(), policy_name="output_toxicity_check",
            policy_version="1.5", evaluator="toxicity_classifier_v1",
            score=round(random.uniform(0.7, 0.95) if toxicity_flag else random.uniform(0.0, 0.1), 3),
            threshold=0.6, allow_block_escalate=("block" if toxicity_flag else "allow"),
            reason_code=("toxic_content" if toxicity_flag else ""), reviewer_id=""
        ))
        if high_risk_without_approval:
            guardrail_rows.append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), policy_name="high_risk_action_approval",
                policy_version="1.0", evaluator="policy_engine", score=0.0, threshold=1.0,
                allow_block_escalate="bypass", reason_code="approval_bypassed", reviewer_id=""
            ))

        # ---- Outcome ----
        escalated = random.random() < (0.06 if not spike_day else 0.11)
        failed = (finish_status == "recovered_after_retry" and random.random() < 0.08) or \
                 (any(r["status"] == "error" for r in tool_rows[-tool_call_count:]) and random.random() < 0.15)
        if pii_egress or toxicity_flag:
            outcome = "blocked_policy"
        elif failed:
            outcome = "failed"
        elif escalated:
            outcome = "escalated_human"
        else:
            outcome = "resolved"

        risk_tier = "high" if any(t["risk_class"] == "high" for t in TOOLS[:0]) else \
            ("high" if tool_call_count and random.random() < 0.15 else
             ("medium" if tool_call_count else "low"))

        step_count = 1 + n_llm_calls + 1 + tool_call_count + (2 if not high_risk_without_approval else 3)
        total_latency = int(total_llm_latency + retrieval_latency + total_tool_latency +
                             random.randint(50, 200))
        workflow_cost = round(total_cost + total_tool_cost + retrieval_cost, 5)

        workflow_rows.append(dict(
            workflow_id=workflow_id, ml_app=ML_APP, service=SERVICE, env=ENV, version=VERSION,
            use_case=USE_CASE, business_unit=BUSINESS_UNIT, tenant=tenant, channel=channel,
            risk_tier=risk_tier, user_hash=user_hash, session_id=session_id,
            start_ts=ts.isoformat(), outcome=outcome,
            total_latency_ms=total_latency, total_cost_usd=workflow_cost,
            llm_cost_usd=round(total_cost, 5), tool_cost_usd=round(total_tool_cost, 5),
            retrieval_cost_usd=retrieval_cost,
            llm_call_count=n_llm_calls, tool_call_count=tool_call_count,
            step_count=step_count, loop_count=loop_count
        ))

# ---- Incident events (derived from the two seeded storylines) ----
if INCIDENT_TRACE_IDS["injection"]:
    incident_rows.append(dict(
        incident_id="INC-2026-0611", severity="Sev2",
        detected_ts=(START_DATE + timedelta(days=11, hours=14, minutes=20)).isoformat(),
        resolved_ts=(START_DATE + timedelta(days=12, hours=9, minutes=5)).isoformat(),
        affected_workflows=len(INCIDENT_TRACE_IDS["injection"]),
        affected_users=len(set(INCIDENT_TRACE_IDS["injection"])),
        root_cause_category="prompt_injection_policy_bypass",
        linked_trace_ids=";".join(INCIDENT_TRACE_IDS["injection"][:20]),
        detection_source="guardrail_anomaly_monitor",
        mitigation="Tightened injection_classifier_v3 threshold from 0.75 to 0.68; added secondary "
                   "human-review gate on refund_issue tool for flagged sessions.",
        recurrence_flag="false"
    ))

incident_rows.append(dict(
    incident_id="INC-2026-0621", severity="Sev1",
    detected_ts=(START_DATE + timedelta(days=20, hours=10, minutes=5)).isoformat(),
    resolved_ts=(START_DATE + timedelta(days=21, hours=6, minutes=40)).isoformat(),
    affected_workflows="~35% of workflows on days 21-22",
    affected_users="n/a (aggregate)",
    root_cause_category="provider_rate_limit_cascade",
    linked_trace_ids="",
    detection_source="cost_and_latency_anomaly_monitor",
    mitigation="Added request queuing + provider fallback pre-routing ahead of known promo windows; "
               "raised primary provider quota tier.",
    recurrence_flag="false"
))

# ---- Release / evaluation event log ----
# Models the v14 -> v15 prompt rollout and rollback that drives the groundedness/citation-accuracy
# dip seeded into the retrieval spans above (see is_release_regression_window).
release_rows = [
    dict(
        event_id="REL-2026-0608", event_type="release",
        ts=(START_DATE + timedelta(days=7, hours=8, minutes=0)).isoformat(),
        artefact="prompt", from_version="v14", to_version="v15",
        golden_set_accuracy_pct=79.2, regression_test_pass_rate_pct=81.5,
        canary_health="degraded",
        notes="Prompt v15 rolled out to improve refund-policy phrasing; canary evaluation flagged "
              "a groundedness/citation-accuracy regression within 4 hours of rollout."
    ),
    dict(
        event_id="REL-2026-0609", event_type="rollback",
        ts=(START_DATE + timedelta(days=8, hours=11, minutes=30)).isoformat(),
        artefact="prompt", from_version="v15", to_version="v14",
        golden_set_accuracy_pct=91.8, regression_test_pass_rate_pct=97.4,
        canary_health="healthy",
        notes="Rolled back to v14 after golden-set accuracy and regression pass rate both breached "
              "release-gate thresholds; v15 held for revision before re-attempting rollout."
    ),
]

# ---- Write raw CSVs ----
def write_csv(path, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

write_csv(os.path.join(RAW_DIR, "workflow_trace.csv"), workflow_rows)
write_csv(os.path.join(RAW_DIR, "llm_span.csv"), llm_rows)
write_csv(os.path.join(RAW_DIR, "retrieval_span.csv"), retrieval_rows)
write_csv(os.path.join(RAW_DIR, "tool_span.csv"), tool_rows)
write_csv(os.path.join(RAW_DIR, "guardrail_span.csv"), guardrail_rows)
write_csv(os.path.join(RAW_DIR, "incident_event.csv"), incident_rows)
write_csv(os.path.join(RAW_DIR, "release_event.csv"), release_rows)

print(f"workflows={len(workflow_rows)} llm_spans={len(llm_rows)} retrieval_spans={len(retrieval_rows)} "
      f"tool_spans={len(tool_rows)} guardrail_spans={len(guardrail_rows)} incidents={len(incident_rows)} "
      f"release_events={len(release_rows)}")

# Aggregation step lives in aggregate_dashboard_summary.py
