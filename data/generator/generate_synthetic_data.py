#!/usr/bin/env python3
"""
Synthetic telemetry generator for the GenAI Observability demo.

Config-driven: all scenario detail (time period, tenants, models, tools,
guardrails, storylines) lives in config.json alongside this script, not in
code. This lets you:

  - extend the time period by editing global.start_date / global.end_date
  - add more use cases *additively* by appending an entry to `scenarios` --
    each enabled scenario gets its own deterministic RNG stream and its rows
    are appended into the same shared CSVs, so adding a new use case grows
    the dataset without perturbing the numbers already produced by existing
    scenarios (re-running with the same config always reproduces the same
    output).

Output follows the telemetry contract defined in the companion source
documents (AI Observability Metrics Catalogue + Datadog Implementation
Addendum): a workflow trace plus span types (llm, retrieval, tool,
guardrail) and small incident_event / release_event tables.

Usage:
    python3 generate_synthetic_data.py [path/to/config.json]

Writes raw span-level CSVs to ../synthetic/raw/. Run aggregate_dashboard_
summary.py afterwards to (re)build dashboard/data/dashboard_summary.json.
"""

import csv
import json
import os
import random
import sys
import uuid
import zlib
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(__file__)
DEFAULT_CONFIG_PATH = os.path.join(HERE, "config.json")
RAW_DIR = os.path.join(HERE, "..", "synthetic", "raw")

TOOL_COST_BY_RISK_DEFAULT = {"low": 0.0015, "medium": 0.012, "high": 0.035}


def load_config(path):
    with open(path) as f:
        return json.load(f)


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def stable_seed(*parts):
    """Deterministic seed derived from arbitrary strings/ints, independent of
    Python's per-process hash randomization (so `hash()` is not safe here)."""
    s = "|".join(str(p) for p in parts)
    return zlib.crc32(s.encode("utf-8"))


def in_window(idx, storyline):
    if not storyline or not storyline.get("enabled", False):
        return False
    return storyline["day_start"] <= idx <= storyline["day_end"]


def offset_ts(start_date, offset):
    return start_date + timedelta(days=offset["days"], hours=offset.get("hours", 0), minutes=offset.get("minutes", 0))


def weighted_choice(rnd, options_weights):
    options = list(options_weights.keys())
    weights = list(options_weights.values())
    return rnd.choices(options, weights=weights)[0]


def build_selection_basis(dtype, selected, order_value, claim_age, groundedness, drnd):
    """Structured, externally-inspectable reasons for the selected action.
    NOT a dump of model chain-of-thought (see docs/decision-contract.md §5.1):
    each item is a short grounded fact/flag an auditor can verify."""
    if dtype == "refund_eligibility":
        if selected == "approve_standard_refund":
            b = ["damaged_item_confirmed", f"claim_within_30_day_window={claim_age <= 30}",
                 f"order_value_below_auto_limit={order_value < 300}"]
        elif selected == "reject_refund":
            b = ["policy_condition_not_met", f"claim_age_days={claim_age}"]
        else:
            b = [f"order_value_above_auto_limit={order_value >= 300}", "requires_human_judgement"]
    elif dtype == "high_risk_tool_invocation":
        if selected == "proceed_with_action":
            b = ["identity_verified", "action_within_agent_authority", f"groundedness={groundedness}"]
        elif selected == "request_human_approval":
            b = ["high_risk_write_action", "approval_policy_requires_review"]
        else:
            b = ["preconditions_not_satisfied", "declined_by_policy"]
    elif dtype == "escalation_vs_autoresolve":
        b = ["confidence_below_autoresolve_threshold", "routed_to_human_queue"] if selected == "escalate_for_manual_review" \
            else ["sufficient_evidence", "within_autoresolve_policy"]
    else:  # guardrail_override
        b = ["action_flagged_by_policy", "proceeded_without_required_review", "flagged_for_post_hoc_audit"]
    return b


def generate_scenario(scenario, global_cfg, start_date, days, rows):
    """Generates all spans/rows for one use-case scenario and appends them
    into the shared `rows` dict of lists (additive across scenarios)."""
    sid = scenario["id"]
    rnd = random.Random(stable_seed(global_cfg.get("random_seed", 42), sid))

    tenants = scenario["tenants"]
    channel_weights = scenario["channels"]
    use_case = scenario["use_case"]
    business_unit = scenario["business_unit"]
    ml_app = scenario["ml_app"]
    service = scenario["service"]
    env = scenario.get("env", "production")
    version = scenario.get("version", "1.0.0")

    primary = scenario["primary_model"]
    fallback = scenario["fallback_model"]

    retrievers = [tuple(r) for r in scenario["retrievers"]]
    tools = scenario["tools"]
    tool_cost_by_risk = scenario.get("tool_cost_by_risk", TOOL_COST_BY_RISK_DEFAULT)

    guardrails = scenario["guardrails"]
    inj_cfg = guardrails["injection_scan"]
    pii_cfg = guardrails["pii_scan"]
    tox_cfg = guardrails["toxicity_scan"]
    approval_cfg = guardrails["approval_policy"]

    vol = scenario["volume"]
    esc = scenario.get("escalation_rate", {"normal": 0.06, "spike": 0.11})

    storylines = scenario.get("storylines", {})
    release_sl = storylines.get("release_regression", {"enabled": False})
    injection_sl = storylines.get("injection_cluster", {"enabled": False})
    ratelimit_sl = storylines.get("rate_limit_spike", {"enabled": False})

    def base_volume_for_day(idx, weekday):
        base = vol["base_daily"] + idx * vol.get("growth_per_day", 0)
        if weekday >= 5:
            base = base * vol.get("weekend_dip_factor", 1.0)
        if in_window(idx, ratelimit_sl):
            base = base * ratelimit_sl.get("volume_multiplier", 1.0)
        return int(base)

    injection_trace_ids = []

    for i in range(days):
        d = start_date + timedelta(days=i)
        idx = i
        n_workflows = base_volume_for_day(idx, d.weekday()) + rnd.randint(-vol.get("jitter", 15), vol.get("jitter", 15))
        injection_day = in_window(idx, injection_sl)
        spike_day = in_window(idx, ratelimit_sl)
        release_window = in_window(idx, release_sl)
        active_prompt_version = release_sl.get("to_version", "v2") if release_window else release_sl.get("from_version", "v1")

        for _ in range(max(n_workflows, 1)):
            workflow_id = str(uuid.uuid4())
            ts = d + timedelta(seconds=rnd.randint(0, 86399))
            tenant = rnd.choice(tenants)
            channel = weighted_choice(rnd, channel_weights)
            session_id = str(uuid.uuid4())
            user_hash = uuid.uuid4().hex[:12]

            # ---- Guardrail: input scan (prompt injection) ----
            is_injection_attempt = False
            if injection_day and rnd.random() < injection_sl.get("rate", 0.15):
                is_injection_attempt = True
            elif rnd.random() < inj_cfg.get("background_rate", 0.008):
                is_injection_attempt = True

            input_block = False
            if is_injection_attempt:
                caught = rnd.random() < inj_cfg.get("catch_rate", 0.92)
                input_block = caught
                rows["guardrail"].append(dict(
                    workflow_id=workflow_id, ts=ts.isoformat(), policy_name=inj_cfg["name"],
                    policy_version=inj_cfg["version"], evaluator=inj_cfg["evaluator"],
                    score=round(rnd.uniform(0.82, 0.99), 3), threshold=inj_cfg.get("threshold", 0.75),
                    allow_block_escalate=("block" if caught else "allow"),
                    reason_code="prompt_injection_detected", reviewer_id=""
                ))
                if not caught:
                    injection_trace_ids.append(workflow_id)
            else:
                rows["guardrail"].append(dict(
                    workflow_id=workflow_id, ts=ts.isoformat(), policy_name=inj_cfg["name"],
                    policy_version=inj_cfg["version"], evaluator=inj_cfg["evaluator"],
                    score=round(rnd.uniform(0.0, 0.15), 3), threshold=inj_cfg.get("threshold", 0.75),
                    allow_block_escalate="allow", reason_code="", reviewer_id=""
                ))

            if input_block:
                rows["workflow"].append(dict(
                    workflow_id=workflow_id, ml_app=ml_app, service=service, env=env, version=version,
                    use_case=use_case, business_unit=business_unit, tenant=tenant, channel=channel,
                    risk_tier="high", user_hash=user_hash, session_id=session_id,
                    start_ts=ts.isoformat(), outcome="blocked_policy",
                    total_latency_ms=rnd.randint(120, 300), total_cost_usd=0.0,
                    llm_cost_usd=0.0, tool_cost_usd=0.0, retrieval_cost_usd=0.0,
                    llm_call_count=0, tool_call_count=0, step_count=1, loop_count=0
                ))
                continue

            # ---- Rate limit / fallback dynamics (spike days) ----
            rate_limited = spike_day and rnd.random() < ratelimit_sl.get("rate_limit_prob", 0.30)
            used_fallback = rate_limited and rnd.random() < ratelimit_sl.get("fallback_prob", 0.75)

            # ---- Retrieval span ----
            retriever, query_type = rnd.choice(retrievers)
            retrieval_latency = max(30, int(rnd.gauss(180, 60)))
            if spike_day:
                retrieval_latency = int(retrieval_latency * 1.4)
            relevance = round(rnd.uniform(0.55, 0.98), 3)
            retrieval_cost = round(rnd.uniform(0.0003, 0.0009), 5)

            groundedness = relevance * rnd.uniform(0.88, 1.03)
            citation_accuracy = relevance * rnd.uniform(0.85, 1.05)
            if release_window:
                groundedness *= rnd.uniform(0.55, 0.72)
                citation_accuracy *= rnd.uniform(0.55, 0.75)
            groundedness = round(max(0.0, min(1.0, groundedness)), 3)
            citation_accuracy = round(max(0.0, min(1.0, citation_accuracy)), 3)
            retrieval_hit = relevance >= 0.62
            hallucination_flag = (groundedness < 0.55 and rnd.random() < 0.15) or rnd.random() < 0.004
            abstention_flag = (not hallucination_flag) and groundedness < 0.4 and rnd.random() < 0.30

            source_ids_this_wf = f"{retriever}:{rnd.randint(1000,9999)}"
            source_freshness_this_wf = rnd.randint(0, 45)
            rows["retrieval"].append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), retriever=retriever, index=retriever,
                query_type=query_type, top_k=5,
                source_ids=source_ids_this_wf, source_authority="approved",
                source_freshness_days=source_freshness_this_wf,
                retrieval_latency_ms=retrieval_latency, relevance_score=relevance,
                retrieval_cost_usd=retrieval_cost, retrieval_hit=retrieval_hit,
                groundedness_score=groundedness, citation_accuracy_score=citation_accuracy,
                hallucination_flag=hallucination_flag, abstention_flag=abstention_flag
            ))

            # ---- LLM span(s) ----
            n_llm_calls = 1
            loop_count = 0
            if rnd.random() < 0.06:
                n_llm_calls += 1
                loop_count = 1
            if rate_limited:
                n_llm_calls += 1

            total_cost = 0.0
            total_llm_latency = 0
            finish_status = "success"
            for call_i in range(n_llm_calls):
                provider, model = primary["provider"], primary["model"]
                model_version = primary.get("model_version", "")
                status = "success"
                finish_reason = "stop"
                if rate_limited and call_i == 0:
                    status = "error"
                    finish_reason = "rate_limit_error"
                elif rate_limited and call_i == n_llm_calls - 1 and used_fallback:
                    provider, model = fallback["provider"], fallback["model"]
                    model_version = fallback.get("model_version", "")

                input_tokens = rnd.randint(350, 1400)
                output_tokens = rnd.randint(60, 420)
                latency = max(200, int(rnd.gauss(950, 300)))
                if spike_day:
                    latency = int(latency * rnd.uniform(1.3, 2.2))
                if status == "error":
                    latency = int(latency * 0.4)
                    cost = 0.0
                else:
                    rate_in, rate_out = (primary["rate_in_per_1k"], primary["rate_out_per_1k"]) \
                        if model == primary["model"] else (fallback["rate_in_per_1k"], fallback["rate_out_per_1k"])
                    cost = round((input_tokens / 1000) * rate_in + (output_tokens / 1000) * rate_out, 5)

                total_cost += cost
                total_llm_latency += latency
                rows["llm"].append(dict(
                    workflow_id=workflow_id, ts=ts.isoformat(), provider=provider, model=model,
                    model_version=model_version, operation="chat.completions", prompt_version=active_prompt_version,
                    temperature=0.2, input_tokens=input_tokens, output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens, cost_usd=cost, latency_ms=latency,
                    status=status, finish_reason=finish_reason
                ))
                if status == "error":
                    finish_status = "recovered_after_retry"

            # ---- Tool span(s) ----
            n_tools = rnd.choices([0, 1, 2, 3], weights=[0.10, 0.45, 0.35, 0.10])[0]
            tool_call_count = 0
            total_tool_latency = 0
            total_tool_cost = 0.0
            high_risk_without_approval = False
            tool_errors_this_wf = 0
            write_tool_name = None
            write_tool_status = None
            write_tool_approval_required = False
            write_tool_approval_status = None
            for _ in range(n_tools):
                tool = rnd.choice(tools)
                approval_required = tool["risk_class"] in ("medium", "high")
                approval_status = "n/a"
                if approval_required:
                    approval_status = "approved" if rnd.random() < 0.97 else "auto_approved_no_review"
                    if approval_status == "auto_approved_no_review" and tool["risk_class"] == "high":
                        high_risk_without_approval = True
                latency = max(80, int(rnd.gauss(320, 120)))
                status = "success" if rnd.random() < 0.96 else "error"
                error_type = "" if status == "success" else rnd.choice(
                    ["timeout", "schema_validation_error", "downstream_5xx"])
                tool_cost = round(tool_cost_by_risk[tool["risk_class"]] * rnd.uniform(0.85, 1.15), 5) \
                    if status == "success" else 0.0
                rows["tool"].append(dict(
                    workflow_id=workflow_id, ts=ts.isoformat(), tool_name=tool["name"],
                    tool_version=tool["version"], action_type=tool["action_type"],
                    read_or_write=tool["read_or_write"], risk_class=tool["risk_class"],
                    approval_required=approval_required, approval_status=approval_status,
                    latency_ms=latency, status=status, error_type=error_type, cost_usd=tool_cost
                ))
                if tool["read_or_write"] == "write" and write_tool_name is None:
                    write_tool_name = tool["name"]
                    write_tool_status = status
                    write_tool_approval_required = approval_required
                    write_tool_approval_status = approval_status
                if status == "error":
                    tool_errors_this_wf += 1
                total_tool_latency += latency
                total_tool_cost += tool_cost
                tool_call_count += 1

            # ---- Guardrail: output scan ----
            pii_egress = rnd.random() < pii_cfg.get("rate", 0.004)
            toxicity_flag = rnd.random() < tox_cfg.get("rate", 0.002)
            rows["guardrail"].append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), policy_name=pii_cfg["name"],
                policy_version=pii_cfg["version"], evaluator=pii_cfg["evaluator"],
                score=round(rnd.uniform(0.85, 0.99) if pii_egress else rnd.uniform(0.0, 0.2), 3),
                threshold=pii_cfg.get("threshold", 0.8), allow_block_escalate=("block" if pii_egress else "allow"),
                reason_code=("pii_detected" if pii_egress else ""), reviewer_id=""
            ))
            rows["guardrail"].append(dict(
                workflow_id=workflow_id, ts=ts.isoformat(), policy_name=tox_cfg["name"],
                policy_version=tox_cfg["version"], evaluator=tox_cfg["evaluator"],
                score=round(rnd.uniform(0.7, 0.95) if toxicity_flag else rnd.uniform(0.0, 0.1), 3),
                threshold=tox_cfg.get("threshold", 0.6), allow_block_escalate=("block" if toxicity_flag else "allow"),
                reason_code=("toxic_content" if toxicity_flag else ""), reviewer_id=""
            ))
            if high_risk_without_approval:
                rows["guardrail"].append(dict(
                    workflow_id=workflow_id, ts=ts.isoformat(), policy_name=approval_cfg["name"],
                    policy_version=approval_cfg["version"], evaluator=approval_cfg["evaluator"],
                    score=0.0, threshold=1.0, allow_block_escalate="bypass",
                    reason_code="approval_bypassed", reviewer_id=""
                ))

            # ---- Outcome ----
            escalated = rnd.random() < (esc["spike"] if spike_day else esc["normal"])
            failed = (finish_status == "recovered_after_retry" and rnd.random() < 0.08) or \
                     (tool_errors_this_wf > 0 and rnd.random() < 0.15)
            if pii_egress or toxicity_flag:
                outcome = "blocked_policy"
            elif failed:
                outcome = "failed"
            elif escalated:
                outcome = "escalated_human"
            else:
                outcome = "resolved"

            risk_tier = "high" if (tool_call_count and rnd.random() < 0.15) else \
                ("medium" if tool_call_count else "low")

            step_count = 1 + n_llm_calls + 1 + tool_call_count + (2 if not high_risk_without_approval else 3)
            total_latency = int(total_llm_latency + retrieval_latency + total_tool_latency +
                                 rnd.randint(50, 200))
            workflow_cost = round(total_cost + total_tool_cost + retrieval_cost, 5)

            rows["workflow"].append(dict(
                workflow_id=workflow_id, ml_app=ml_app, service=service, env=env, version=version,
                use_case=use_case, business_unit=business_unit, tenant=tenant, channel=channel,
                risk_tier=risk_tier, user_hash=user_hash, session_id=session_id,
                start_ts=ts.isoformat(), outcome=outcome,
                total_latency_ms=total_latency, total_cost_usd=workflow_cost,
                llm_cost_usd=round(total_cost, 5), tool_cost_usd=round(total_tool_cost, 5),
                retrieval_cost_usd=retrieval_cost,
                llm_call_count=n_llm_calls, tool_call_count=tool_call_count,
                step_count=step_count, loop_count=loop_count
            ))

            # ---- Decision record (first-class decision object) ----
            # Emitted on a SEPARATE RNG stream (drnd) keyed by workflow_id so it never
            # perturbs the main `rnd` sequence -- existing CSV numbers reproduce exactly.
            # Only *consequential* workflows (a write action, an override, or an escalation)
            # produce a decision; pure read/execution workflows do not (decision-contract.md §2).
            dcfg = scenario.get("decisions", {})
            if dcfg.get("enabled"):
                dtypes = dcfg.get("types", {})
                dtype = None
                if high_risk_without_approval and "guardrail_override" in dtypes:
                    dtype = "guardrail_override"
                elif write_tool_name == "refund_issue" and "refund_eligibility" in dtypes:
                    dtype = "refund_eligibility"
                elif write_tool_name in ("address_update", "loyalty_credit") and "high_risk_tool_invocation" in dtypes:
                    dtype = "high_risk_tool_invocation"
                elif escalated and "escalation_vs_autoresolve" in dtypes:
                    dtype = "escalation_vs_autoresolve"

                if dtype:
                    dspec = dtypes[dtype]
                    drnd = random.Random(stable_seed(global_cfg.get("random_seed", 42), sid, "decision", workflow_id))
                    options = dspec.get("options", [])

                    if dtype == "refund_eligibility":
                        selected = "escalate_for_manual_review" if outcome == "escalated_human" else \
                            ("reject_refund" if outcome == "blocked_policy" else "approve_standard_refund")
                    elif dtype == "high_risk_tool_invocation":
                        selected = "request_human_approval" if outcome == "escalated_human" else \
                            ("decline_action" if outcome == "blocked_policy" else "proceed_with_action")
                    elif dtype == "escalation_vs_autoresolve":
                        selected = "escalate_for_manual_review" if escalated else "auto_resolve"
                    else:
                        selected = "proceed_with_override"

                    policy_result = "bypass" if dtype == "guardrail_override" else \
                        ("fail" if outcome == "blocked_policy" else "pass")

                    approval_required_dec = write_tool_approval_required if write_tool_name else (dtype == "guardrail_override")
                    approval_status_dec = write_tool_approval_status if write_tool_name else (
                        "auto_approved_no_review" if dtype == "guardrail_override" else "not_required")
                    if selected in ("escalate_for_manual_review", "request_human_approval"):
                        approver_id = f"human-review-{drnd.randint(200, 499)}"
                    elif policy_result == "bypass":
                        approver_id = ""  # no reviewer -- precisely the governance signal
                    elif approval_required_dec:
                        approver_id = f"ops-approver-{drnd.randint(10, 99)}"
                    else:
                        approver_id = ""

                    order_value = round(drnd.uniform(24.0, 480.0), 2)
                    claim_age = drnd.randint(1, 40)
                    customer_tier = drnd.choice(["standard", "loyalty_silver", "loyalty_gold"])
                    input_facts = {"order_value": order_value, "customer_tier": customer_tier,
                                   "claim_age_days": claim_age, "channel": channel}
                    basis = build_selection_basis(dtype, selected, order_value, claim_age, groundedness, drnd)
                    # Illustrative confidence (loosely tracks groundedness). In production this is
                    # emitted by the agent or a rationale-summariser, never back-filled here.
                    confidence = round(min(0.99, max(0.4, groundedness * drnd.uniform(0.95, 1.03))), 2)
                    amount = order_value if (dtype == "refund_eligibility" and selected == "approve_standard_refund") else None

                    rows["decision"].append(dict(
                        decision_id=f"DEC-{ts.strftime('%Y%m%d')}-{workflow_id[:6]}",
                        workflow_id=workflow_id, ts=ts.isoformat(), decision_type=dtype,
                        actor_type="agent", actor_name=ml_app, actor_version=version,
                        objective=dspec.get("objective", ""),
                        input_facts=json.dumps(input_facts),
                        evidence_refs=json.dumps([retriever, source_ids_this_wf]),
                        evidence_freshness_days=source_freshness_this_wf,
                        groundedness_score=groundedness,
                        options_evaluated=json.dumps(options),
                        selected_action=selected,
                        selection_basis=json.dumps(basis),
                        confidence=confidence,
                        policy_evaluations=json.dumps([{"policy_id": dspec.get("policy_id", ""),
                                                        "version": dspec.get("policy_version", ""),
                                                        "result": policy_result}]),
                        authority=json.dumps({"approval_required": bool(approval_required_dec),
                                              "approval_status": approval_status_dec,
                                              "approver_id": approver_id}),
                        tool_action=json.dumps({"tool": write_tool_name or "", "result": write_tool_status or "n/a"}),
                        business_outcome=json.dumps({"outcome": outcome, "amount": amount}),
                        owner=dspec.get("owner", ""), risk_tier=risk_tier,
                    ))

    # ---- Incident events (derived from this scenario's storylines) ----
    if injection_sl.get("enabled") and injection_trace_ids:
        rows["incident"].append(dict(
            incident_id=injection_sl["incident_id"], severity=injection_sl["severity"],
            detected_ts=offset_ts(start_date, injection_sl["detected_offset"]).isoformat(),
            resolved_ts=offset_ts(start_date, injection_sl["resolved_offset"]).isoformat(),
            affected_workflows=len(injection_trace_ids),
            affected_users=len(set(injection_trace_ids)),
            root_cause_category=injection_sl["root_cause_category"],
            linked_trace_ids=";".join(injection_trace_ids[:20]),
            detection_source=injection_sl["detection_source"],
            mitigation=injection_sl["mitigation"],
            recurrence_flag="false"
        ))

    if ratelimit_sl.get("enabled"):
        rows["incident"].append(dict(
            incident_id=ratelimit_sl["incident_id"], severity=ratelimit_sl["severity"],
            detected_ts=offset_ts(start_date, ratelimit_sl["detected_offset"]).isoformat(),
            resolved_ts=offset_ts(start_date, ratelimit_sl["resolved_offset"]).isoformat(),
            affected_workflows=ratelimit_sl.get("affected_workflows_note", "n/a"),
            affected_users="n/a (aggregate)",
            root_cause_category=ratelimit_sl["root_cause_category"],
            linked_trace_ids="",
            detection_source=ratelimit_sl["detection_source"],
            mitigation=ratelimit_sl["mitigation"],
            recurrence_flag="false"
        ))

    # ---- Release / evaluation event log ----
    if release_sl.get("enabled"):
        rows["release"].append(dict(
            event_id=release_sl["release_event_id"], event_type="release",
            ts=(start_date + timedelta(days=release_sl["day_start"], hours=8, minutes=0)).isoformat(),
            artefact="prompt", from_version=release_sl["from_version"], to_version=release_sl["to_version"],
            golden_set_accuracy_pct=release_sl["release_golden_set_accuracy_pct"],
            regression_test_pass_rate_pct=release_sl["release_regression_pass_rate_pct"],
            canary_health="degraded",
            notes=release_sl["release_notes"]
        ))
        rows["release"].append(dict(
            event_id=release_sl["rollback_event_id"], event_type="rollback",
            ts=(start_date + timedelta(days=release_sl["day_end"], hours=11, minutes=30)).isoformat(),
            artefact="prompt", from_version=release_sl["to_version"], to_version=release_sl["from_version"],
            golden_set_accuracy_pct=release_sl["rollback_golden_set_accuracy_pct"],
            regression_test_pass_rate_pct=release_sl["rollback_regression_pass_rate_pct"],
            canary_health="healthy",
            notes=release_sl["rollback_notes"]
        ))


def write_csv(path, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    cfg = load_config(config_path)
    g = cfg["global"]
    start_date = parse_date(g["start_date"])
    end_date = parse_date(g["end_date"])
    days = (end_date - start_date).days + 1
    if days < 1:
        raise ValueError("global.end_date must be on or after global.start_date")

    os.makedirs(RAW_DIR, exist_ok=True)

    rows = dict(workflow=[], llm=[], retrieval=[], tool=[], guardrail=[], decision=[], incident=[], release=[])

    enabled_scenarios = [s for s in cfg["scenarios"] if s.get("enabled", True)]
    if not enabled_scenarios:
        raise ValueError("No scenarios are enabled in config.json — nothing to generate.")

    for scenario in enabled_scenarios:
        generate_scenario(scenario, g, start_date, days, rows)

    write_csv(os.path.join(RAW_DIR, "workflow_trace.csv"), rows["workflow"])
    write_csv(os.path.join(RAW_DIR, "llm_span.csv"), rows["llm"])
    write_csv(os.path.join(RAW_DIR, "retrieval_span.csv"), rows["retrieval"])
    write_csv(os.path.join(RAW_DIR, "tool_span.csv"), rows["tool"])
    write_csv(os.path.join(RAW_DIR, "guardrail_span.csv"), rows["guardrail"])
    write_csv(os.path.join(RAW_DIR, "decision_span.csv"), rows["decision"])
    write_csv(os.path.join(RAW_DIR, "incident_event.csv"), rows["incident"])
    write_csv(os.path.join(RAW_DIR, "release_event.csv"), rows["release"])

    print(f"scenarios={[s['id'] for s in enabled_scenarios]} days={days} "
          f"workflows={len(rows['workflow'])} llm_spans={len(rows['llm'])} "
          f"retrieval_spans={len(rows['retrieval'])} tool_spans={len(rows['tool'])} "
          f"guardrail_spans={len(rows['guardrail'])} decisions={len(rows['decision'])} "
          f"incidents={len(rows['incident'])} release_events={len(rows['release'])}")


if __name__ == "__main__":
    main()
