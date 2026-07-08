/* GenAI Project Observability — demo dashboard
   Renders synthetic telemetry from data/dashboard_summary.json.
   No backend, no network calls beyond the local JSON + Chart.js CDN. */

/* Getamazednow AI Design System v1.0 — dark-surface (on-Ink) palette.
   Signal family for accents; semantic on-Ink variants for status colors;
   Stone as the secondary/neutral accent. */
const COLORS = {
  accent: "#5FA8CC",   // gai-signal
  accent2: "#8FC3DE",  // gai-signal-core
  green: "#6FBF8B",    // gai-success-on-ink
  amber: "#E3A253",    // gai-warning-on-ink
  red: "#E08585",      // gai-error-on-ink
  blue: "#7FB3C2",     // gai-info-on-ink
  stone: "#A8A17B",    // gai-stone
  grid: "rgba(255,255,255,0.06)",
  text: "#B7BEC2",     // gai-neutral-300
};

if (typeof Chart === "undefined") {
  document.querySelector("main").innerHTML =
    `<div class="panel" style="color:#E08585;">Chart.js failed to load from the CDN (jsDelivr and cdnjs both unreachable). ` +
    `Check your network connection, or download chart.umd.min.js locally and reference it from index.html instead of a CDN.</div>`;
  throw new Error("Chart.js not loaded — aborting dashboard init.");
}

Chart.defaults.color = COLORS.text;
Chart.defaults.font.family = "'Inter', 'Segoe UI', Roboto, sans-serif";
Chart.defaults.font.size = 11;

function fmtUsd(v, digits = 2) {
  return "$" + Number(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function fmtInt(v) {
  return Number(v).toLocaleString();
}
function shortDate(d) {
  const dt = new Date(d + "T00:00:00Z");
  return dt.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}

function kpiCard(label, value, sub, cls = "") {
  return `<div class="kpi-card">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value ${cls}">${value}</div>
      ${sub ? `<div class="kpi-sub">${sub}</div>` : ""}
    </div>`;
}

function baseLineOpts(extra = {}) {
  return Object.assign({
    responsive: true,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { labels: { boxWidth: 12, padding: 14 } } },
    scales: {
      x: { grid: { color: COLORS.grid }, ticks: { maxRotation: 0 } },
      y: { grid: { color: COLORS.grid }, beginAtZero: true },
    },
  }, extra);
}

async function main() {
  const res = await fetch("data/dashboard_summary.json");
  const data = await res.json();
  const daily = data.daily;
  const labels = daily.map(d => shortDate(d.date));
  const h = data.headline;

  document.getElementById("window-pill").textContent =
    `${shortDate(data.scenario.window_start)} – ${shortDate(data.scenario.window_end)} (${data.scenario.window_days}d)`;

  renderExecTab(data, labels);
  renderEngTab(data, labels);
  renderSecTab(data, labels);
  renderCostTab(data, labels);
  renderAgentTab(data, labels);
  renderRagTab(data, labels);
  renderReleaseTab(data, labels);
  wireTabs();
}

/* ---------------- EXECUTIVE AI HEALTH ---------------- */
function renderExecTab(data, labels) {
  const daily = data.daily;
  const h = data.headline;
  const totalPolicyViolations = daily.reduce((s, d) => s + d.policy_approval_bypasses + d.prompt_injection_bypassed, 0);

  document.getElementById("exec-kpis").innerHTML = [
    kpiCard("Workflows (30d)", fmtInt(h.total_workflows), data.scenario.use_case),
    kpiCard("Success rate", h.overall_success_rate_pct + "%", "resolved + escalated / total", h.overall_success_rate_pct >= 95 ? "good" : "warn"),
    kpiCard("Cost / successful workflow", fmtUsd(h.overall_cost_per_successful_workflow_usd, 4), "LLM + tool + retrieval cost"),
    kpiCard("Monthly run-rate", fmtUsd(h.forecasted_monthly_runrate_usd), "forecast at current volume"),
    kpiCard("Est. cost avoidance / mo", fmtUsd(h.estimated_cost_avoidance_usd, 0), `vs. ${fmtUsd(h.assumed_human_handled_cost_usd)} human-handled contact (assumption)`, "good"),
    kpiCard("P95 latency (e2e)", fmtInt(h.overall_latency_p95_ms) + " ms", "30-day P95"),
    kpiCard("Incidents (Sev1/Sev2)", fmtInt(h.incident_count), "see incident log below", h.incident_count > 0 ? "warn" : "good"),
    kpiCard("Policy violations", fmtInt(totalPolicyViolations), "approval bypass + injection bypass", totalPolicyViolations > 0 ? "bad" : "good"),
  ].join("");

  new Chart(document.getElementById("chart-volume"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Resolved", data: daily.map(d => d.workflows_resolved), backgroundColor: COLORS.green, stack: "s" },
        { label: "Escalated to human", data: daily.map(d => d.workflows_escalated), backgroundColor: COLORS.blue, stack: "s" },
        { label: "Blocked (policy)", data: daily.map(d => d.workflows_blocked_policy), backgroundColor: COLORS.amber, stack: "s" },
        { label: "Failed", data: daily.map(d => d.workflows_failed), backgroundColor: COLORS.red, stack: "s" },
      ],
    },
    options: baseLineOpts({ scales: { x: { stacked: true, grid: { color: COLORS.grid } }, y: { stacked: true, grid: { color: COLORS.grid } } } }),
  });

  new Chart(document.getElementById("chart-success"), {
    type: "line",
    data: { labels, datasets: [{ label: "Success rate %", data: daily.map(d => d.success_rate_pct), borderColor: COLORS.green, backgroundColor: "transparent", tension: 0.25 }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-cost"), {
    type: "line",
    data: { labels, datasets: [{ label: "Cost / successful workflow (USD)", data: daily.map(d => d.cost_per_successful_workflow_usd), borderColor: COLORS.accent, backgroundColor: "transparent", tension: 0.25 }] },
    options: baseLineOpts(),
  });

  const tenants = data.scenario.tenants;
  const tenantTotals = tenants.map(t => daily.reduce((s, d) => s + (d.workflows_by_tenant[t] || 0), 0));
  const tenantPalette = [COLORS.accent, COLORS.accent2, COLORS.blue, COLORS.green, COLORS.amber, COLORS.red];
  new Chart(document.getElementById("chart-tenant"), {
    type: "doughnut",
    data: { labels: tenants, datasets: [{ data: tenantTotals, backgroundColor: tenants.map((_, i) => tenantPalette[i % tenantPalette.length]) }] },
    options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } } },
  });

  const useCases = (data.scenario.use_cases || []).map(u => u.use_case_label);
  const ucLabels = useCases.length ? useCases : [data.scenario.use_case];
  const ucTotals = ucLabels.map((_, i) => {
    const key = (data.scenario.use_cases && data.scenario.use_cases[i]) ? data.scenario.use_cases[i].use_case : null;
    return daily.reduce((s, d) => s + (key ? (d.workflows_by_use_case && d.workflows_by_use_case[key]) || 0 : d.workflows_total), 0);
  });
  new Chart(document.getElementById("chart-usecase"), {
    type: "bar",
    data: { labels: ucLabels, datasets: [{ data: ucTotals, backgroundColor: tenantPalette.slice(0, ucLabels.length) }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { grid: { color: COLORS.grid } }, y: { grid: { display: false } } } },
  });

  const llmCost = daily.reduce((s, d) => s + d.llm_cost_usd, 0);
  const toolCost = daily.reduce((s, d) => s + d.tool_cost_usd, 0);
  const retrievalCost = daily.reduce((s, d) => s + d.retrieval_cost_usd, 0);
  new Chart(document.getElementById("chart-cost-breakdown"), {
    type: "bar",
    data: {
      labels: ["Model (LLM) cost", "Tool / API cost", "Retrieval cost"],
      datasets: [{ data: [llmCost, toolCost, retrievalCost], backgroundColor: [COLORS.accent, COLORS.blue, COLORS.accent2] }],
    },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { grid: { color: COLORS.grid } }, y: { grid: { display: false } } } },
  });

  const incidentTable = document.getElementById("incident-table");
  const rows = data.incidents.map(inc => {
    const detected = new Date(inc.detected_ts);
    const resolved = new Date(inc.resolved_ts);
    const mttrHrs = ((resolved - detected) / 3600000).toFixed(1);
    const sevClass = inc.severity === "Sev1" ? "sev-1" : "sev-2";
    return `<tr>
        <td>${inc.incident_id}</td>
        <td><span class="sev-badge ${sevClass}">${inc.severity}</span></td>
        <td>${inc.root_cause_category.replace(/_/g, " ")}</td>
        <td>${detected.toISOString().slice(0, 16).replace("T", " ")}</td>
        <td>${mttrHrs} h</td>
        <td>${inc.affected_workflows}</td>
        <td>${inc.detection_source.replace(/_/g, " ")}</td>
      </tr>`;
  }).join("");
  incidentTable.innerHTML = `<thead><tr>
      <th>ID</th><th>Severity</th><th>Root cause</th><th>Detected (UTC)</th><th>MTTR</th><th>Affected workflows</th><th>Detection source</th>
    </tr></thead><tbody>${rows}</tbody>`;
}

/* ---------------- ENGINEERING OPERATIONS ---------------- */
function renderEngTab(data, labels) {
  const daily = data.daily;
  const avg = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;

  document.getElementById("eng-kpis").innerHTML = [
    kpiCard("P50 latency", Math.round(avg(daily.map(d => d.latency_p50_ms))) + " ms", "30-day average"),
    kpiCard("P95 latency", Math.round(avg(daily.map(d => d.latency_p95_ms))) + " ms", "30-day average"),
    kpiCard("P99 latency", Math.round(avg(daily.map(d => d.latency_p99_ms))) + " ms", "30-day average"),
    kpiCard("LLM error rate", (avg(daily.map(d => d.llm_error_rate_pct))).toFixed(2) + "%", "model call failures"),
    kpiCard("Retry rate", (avg(daily.map(d => d.retry_rate_pct))).toFixed(2) + "%", "workflows requiring retry"),
    kpiCard("Rate-limit events", fmtInt(daily.reduce((s, d) => s + d.rate_limit_events, 0)), "30-day total", "warn"),
  ].join("");

  new Chart(document.getElementById("chart-latency-layers"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Model latency P95", data: daily.map(d => d.model_latency_p95_ms), borderColor: COLORS.accent, backgroundColor: "transparent", tension: 0.2 },
        { label: "Retrieval latency P95", data: daily.map(d => d.retrieval_latency_p95_ms), borderColor: COLORS.accent2, backgroundColor: "transparent", tension: 0.2 },
        { label: "Tool latency P95", data: daily.map(d => d.tool_latency_p95_ms), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-latency-pcts"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "P50", data: daily.map(d => d.latency_p50_ms), borderColor: COLORS.green, backgroundColor: "transparent", tension: 0.2 },
        { label: "P95", data: daily.map(d => d.latency_p95_ms), borderColor: COLORS.amber, backgroundColor: "transparent", tension: 0.2 },
        { label: "P99", data: daily.map(d => d.latency_p99_ms), borderColor: COLORS.red, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-error-rates"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "LLM error rate %", data: daily.map(d => d.llm_error_rate_pct), borderColor: COLORS.red, backgroundColor: "transparent", tension: 0.2 },
        { label: "Retry rate %", data: daily.map(d => d.retry_rate_pct), borderColor: COLORS.amber, backgroundColor: "transparent", tension: 0.2 },
        { label: "Tool error rate %", data: daily.map(d => d.tool_error_rate_pct), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-ratelimit"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Rate-limit events", data: daily.map(d => d.rate_limit_events), backgroundColor: COLORS.amber }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-loops"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Loop / replanning events", data: daily.map(d => d.loop_events), backgroundColor: COLORS.accent }] },
    options: baseLineOpts(),
  });

  // Illustrative single-trace waterfall (incident-day workflow: guardrail -> retrieval -> llm (rate-limited retry + fallback) -> tool -> guardrail)
  const steps = [
    { name: "Input guardrail scan", start: 0, dur: 45 },
    { name: "Context retrieval", start: 45, dur: 260 },
    { name: "LLM call #1 (rate-limited, failed)", start: 305, dur: 180 },
    { name: "LLM call #2 (fallback model)", start: 485, dur: 1450 },
    { name: "Tool: refund_issue", start: 1935, dur: 340 },
    { name: "Output guardrail scan", start: 2275, dur: 60 },
  ];
  new Chart(document.getElementById("chart-waterfall"), {
    type: "bar",
    data: {
      labels: steps.map(s => s.name),
      datasets: [
        { label: "start (offset)", data: steps.map(s => s.start), backgroundColor: "transparent" },
        { label: "duration (ms)", data: steps.map(s => s.dur), backgroundColor: [COLORS.blue, COLORS.accent2, COLORS.red, COLORS.amber, COLORS.accent, COLORS.blue] },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ctx.dataset.label === "duration (ms)" ? `${ctx.raw} ms` : null } } },
      scales: {
        x: { stacked: true, grid: { color: COLORS.grid }, title: { display: true, text: "Elapsed time (ms)" } },
        y: { stacked: true, grid: { display: false } },
      },
    },
  });
}

/* ---------------- SECURITY & RESPONSIBLE AI ---------------- */
function renderSecTab(data, labels) {
  const daily = data.daily;
  const totalAttempts = daily.reduce((s, d) => s + d.prompt_injection_attempts, 0);
  const totalBypassed = daily.reduce((s, d) => s + d.prompt_injection_bypassed, 0);
  const totalEgress = daily.reduce((s, d) => s + d.sensitive_data_egress_events, 0);
  const totalToxicity = daily.reduce((s, d) => s + d.toxicity_flags, 0);
  const totalHighRisk = daily.reduce((s, d) => s + d.high_risk_tool_calls, 0);
  const totalApprovalBypass = daily.reduce((s, d) => s + d.policy_approval_bypasses, 0);

  document.getElementById("sec-kpis").innerHTML = [
    kpiCard("Prompt injection attempts", fmtInt(totalAttempts), "30-day total"),
    kpiCard("Injection bypassed", fmtInt(totalBypassed), "guardrail miss → incident", totalBypassed > 0 ? "bad" : "good"),
    kpiCard("Sensitive data egress", fmtInt(totalEgress), "PII/secret leakage events", totalEgress > 0 ? "warn" : "good"),
    kpiCard("Toxicity flags", fmtInt(totalToxicity), "output policy checks"),
    kpiCard("High-risk tool calls", fmtInt(totalHighRisk), "write/refund/address-change"),
    kpiCard("Approval bypasses", fmtInt(totalApprovalBypass), "high-risk action w/o review", totalApprovalBypass > 0 ? "bad" : "good"),
  ].join("");

  new Chart(document.getElementById("chart-injection"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Blocked", data: daily.map(d => d.prompt_injection_blocked), backgroundColor: COLORS.green, stack: "s" },
        { label: "Bypassed (incident)", data: daily.map(d => d.prompt_injection_bypassed), backgroundColor: COLORS.red, stack: "s" },
      ],
    },
    options: baseLineOpts({ scales: { x: { stacked: true, grid: { color: COLORS.grid } }, y: { stacked: true, grid: { color: COLORS.grid } } } }),
  });

  new Chart(document.getElementById("chart-privacy"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Sensitive data egress", data: daily.map(d => d.sensitive_data_egress_events), backgroundColor: COLORS.red },
        { label: "Toxicity flags", data: daily.map(d => d.toxicity_flags), backgroundColor: COLORS.amber },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-highrisk"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "High-risk tool calls", data: daily.map(d => d.high_risk_tool_calls), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 },
        { label: "Approval bypasses", data: daily.map(d => d.policy_approval_bypasses), borderColor: COLORS.red, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  const inc = data.incidents.find(i => i.root_cause_category === "prompt_injection_policy_bypass");
  if (inc) {
    const detected = new Date(inc.detected_ts);
    const resolved = new Date(inc.resolved_ts);
    const mttrHrs = ((resolved - detected) / 3600000).toFixed(1);
    document.getElementById("incident-spotlight").innerHTML = `
      <div class="spotlight-grid">
        <div class="spotlight-item"><div class="label">Severity</div><div class="value"><span class="sev-badge sev-2">${inc.severity}</span></div></div>
        <div class="spotlight-item"><div class="label">Detected</div><div class="value">${detected.toISOString().slice(0,16).replace("T"," ")} UTC</div></div>
        <div class="spotlight-item"><div class="label">MTTR</div><div class="value">${mttrHrs} hours</div></div>
        <div class="spotlight-item"><div class="label">Affected workflows</div><div class="value">${inc.affected_workflows}</div></div>
        <div class="spotlight-item"><div class="label">Detection source</div><div class="value">${inc.detection_source.replace(/_/g," ")}</div></div>
        <div class="spotlight-item"><div class="label">Mitigation</div><div class="value">${inc.mitigation}</div></div>
      </div>`;
  }
}

/* ---------------- AI COST AND CAPACITY ---------------- */
function renderCostTab(data, labels) {
  const daily = data.daily;
  const h = data.headline;
  const sum = (arr) => arr.reduce((a, b) => a + b, 0);

  const totalFallbackCost = sum(daily.map(d => d.fallback_cost_usd));
  const peakQuota = Math.max(...daily.map(d => d.quota_utilization_pct));
  const finalBudgetBurn = daily[daily.length - 1].budget_burn_pct;

  document.getElementById("cost-kpis").innerHTML = [
    kpiCard("Monthly run-rate", fmtUsd(h.forecasted_monthly_runrate_usd), `budget: ${fmtUsd(h.monthly_cost_budget_usd)}`, finalBudgetBurn > 100 ? "bad" : "good"),
    kpiCard("Budget burn (30d)", finalBudgetBurn + "%", "cumulative cost / monthly budget", finalBudgetBurn > 90 ? "warn" : "good"),
    kpiCard("Peak quota utilisation", peakQuota + "%", `of ${fmtInt(h.daily_llm_call_quota)} calls/day`, peakQuota > 90 ? "bad" : "good"),
    kpiCard("Fallback-model cost", fmtUsd(totalFallbackCost, 3), "30-day total, rate-limit routing"),
    kpiCard("Input tokens (30d)", fmtInt(sum(daily.map(d => d.input_tokens_total)))),
    kpiCard("Output tokens (30d)", fmtInt(sum(daily.map(d => d.output_tokens_total)))),
  ].join("");

  new Chart(document.getElementById("chart-tokens"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Input tokens", data: daily.map(d => d.input_tokens_total), borderColor: COLORS.accent2, backgroundColor: "transparent", tension: 0.2 },
        { label: "Output tokens", data: daily.map(d => d.output_tokens_total), borderColor: COLORS.accent, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  const models = Array.from(new Set(daily.flatMap(d => Object.keys(d.cost_by_model_usd || {}))));
  const modelColors = [COLORS.accent, COLORS.blue, COLORS.accent2, COLORS.amber];
  new Chart(document.getElementById("chart-cost-by-model"), {
    type: "bar",
    data: {
      labels,
      datasets: models.map((m, i) => ({
        label: m,
        data: daily.map(d => (d.cost_by_model_usd || {})[m] || 0),
        backgroundColor: modelColors[i % modelColors.length],
        stack: "s",
      })),
    },
    options: baseLineOpts({ scales: { x: { stacked: true, grid: { color: COLORS.grid } }, y: { stacked: true, grid: { color: COLORS.grid } } } }),
  });

  new Chart(document.getElementById("chart-quota"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Quota utilisation %", data: daily.map(d => d.quota_utilization_pct), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 },
        { label: "Quota limit (100%)", data: daily.map(() => 100), borderColor: COLORS.red, borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-budget-burn"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Cumulative cost (USD)", data: daily.map(d => d.cumulative_cost_usd), borderColor: COLORS.green, backgroundColor: "transparent", tension: 0.2 },
        { label: "Monthly budget (USD)", data: daily.map(() => h.monthly_cost_budget_usd), borderColor: COLORS.red, borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-fallback-cost"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Fallback-model cost (USD)", data: daily.map(d => d.fallback_cost_usd), backgroundColor: COLORS.amber }] },
    options: baseLineOpts(),
  });
}

/* ---------------- AGENT BEHAVIOUR AND AGENCY ---------------- */
function renderAgentTab(data, labels) {
  const daily = data.daily;
  const avg = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;

  document.getElementById("agent-kpis").innerHTML = [
    kpiCard("Avg steps / workflow", avg(daily.map(d => d.avg_step_count)).toFixed(2), "30-day average"),
    kpiCard("Avg tool calls / workflow", avg(daily.map(d => d.avg_tool_calls_per_workflow)).toFixed(2), "30-day average"),
    kpiCard("Avg escalation rate", avg(daily.map(d => d.escalation_rate_pct)).toFixed(2) + "%", "workflows requiring a human"),
    kpiCard("Tool call success rate", avg(daily.map(d => d.tool_selection_success_pct)).toFixed(2) + "%", "proxy for tool-selection quality"),
  ].join("");

  new Chart(document.getElementById("chart-steps"), {
    type: "line",
    data: { labels, datasets: [{ label: "Avg step count", data: daily.map(d => d.avg_step_count), borderColor: COLORS.accent, backgroundColor: "transparent", tension: 0.2 }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-toolcalls-avg"), {
    type: "line",
    data: { labels, datasets: [{ label: "Avg tool calls / workflow", data: daily.map(d => d.avg_tool_calls_per_workflow), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 }] },
    options: baseLineOpts(),
  });

  const toolTotals = {};
  daily.forEach(d => {
    Object.entries(d.tool_calls_by_name || {}).forEach(([name, count]) => {
      toolTotals[name] = (toolTotals[name] || 0) + count;
    });
  });
  const toolNames = Object.keys(toolTotals).sort((a, b) => toolTotals[b] - toolTotals[a]);
  new Chart(document.getElementById("chart-tools-by-name"), {
    type: "bar",
    data: { labels: toolNames, datasets: [{ data: toolNames.map(n => toolTotals[n]), backgroundColor: COLORS.accent2 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { grid: { color: COLORS.grid } }, y: { grid: { display: false } } } },
  });

  new Chart(document.getElementById("chart-escalation-rate"), {
    type: "line",
    data: { labels, datasets: [{ label: "Escalation rate %", data: daily.map(d => d.escalation_rate_pct), borderColor: COLORS.amber, backgroundColor: "transparent", tension: 0.2 }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-tool-success"), {
    type: "line",
    data: { labels, datasets: [{ label: "Tool call success %", data: daily.map(d => d.tool_selection_success_pct), borderColor: COLORS.green, backgroundColor: "transparent", tension: 0.2 }] },
    options: baseLineOpts(),
  });
}

/* ---------------- RAG AND GROUNDING QUALITY ---------------- */
function renderRagTab(data, labels) {
  const daily = data.daily;
  const avg = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;

  document.getElementById("rag-kpis").innerHTML = [
    kpiCard("Retrieval hit rate", avg(daily.map(d => d.retrieval_hit_rate_pct)).toFixed(1) + "%", "30-day average"),
    kpiCard("Avg groundedness", avg(daily.map(d => d.avg_groundedness_score)).toFixed(3), "0-1 scale"),
    kpiCard("Avg citation accuracy", avg(daily.map(d => d.avg_citation_accuracy_score)).toFixed(3), "0-1 scale"),
    kpiCard("Hallucination rate", avg(daily.map(d => d.hallucination_rate_pct)).toFixed(2) + "%", "30-day average", avg(daily.map(d => d.hallucination_rate_pct)) > 3 ? "warn" : "good"),
    kpiCard("Abstention rate", avg(daily.map(d => d.abstention_rate_pct)).toFixed(2) + "%", "agent declined, insufficient evidence"),
    kpiCard("Avg source freshness", avg(daily.map(d => d.avg_source_freshness_days)).toFixed(1) + " d", "age of retrieved sources"),
  ].join("");

  new Chart(document.getElementById("chart-hit-rate"), {
    type: "line",
    data: { labels, datasets: [{ label: "Retrieval hit rate %", data: daily.map(d => d.retrieval_hit_rate_pct), borderColor: COLORS.accent2, backgroundColor: "transparent", tension: 0.2 }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-groundedness"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Groundedness score", data: daily.map(d => d.avg_groundedness_score), borderColor: COLORS.accent, backgroundColor: "transparent", tension: 0.2 },
        { label: "Citation accuracy", data: daily.map(d => d.avg_citation_accuracy_score), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-hallucination"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Hallucination rate %", data: daily.map(d => d.hallucination_rate_pct), backgroundColor: COLORS.red }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-abstention"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Abstention rate %", data: daily.map(d => d.abstention_rate_pct), backgroundColor: COLORS.amber }] },
    options: baseLineOpts(),
  });

  new Chart(document.getElementById("chart-freshness"), {
    type: "line",
    data: { labels, datasets: [{ label: "Avg source freshness (days)", data: daily.map(d => d.avg_source_freshness_days), borderColor: COLORS.accent2, backgroundColor: "transparent", tension: 0.2 }] },
    options: baseLineOpts(),
  });
}

/* ---------------- AI RELEASE AND EVALUATION ---------------- */
function renderReleaseTab(data, labels) {
  const daily = data.daily;
  const h = data.headline;
  const latest = daily[daily.length - 1];

  document.getElementById("release-kpis").innerHTML = [
    kpiCard("Current prompt version", latest.active_prompt_version, "active in production"),
    kpiCard("Regression pass rate", latest.regression_pass_rate_pct + "%", "latest eval run", latest.regression_pass_rate_pct >= 95 ? "good" : "warn"),
    kpiCard("Golden-set accuracy", latest.golden_set_accuracy_pct + "%", "latest eval run", latest.golden_set_accuracy_pct >= 90 ? "good" : "warn"),
    kpiCard("Canary health", latest.canary_health, "current status", latest.canary_health === "healthy" ? "good" : "warn"),
    kpiCard("Rollbacks (30d)", fmtInt(h.rollback_count), "release/rollback log below"),
  ].join("");

  new Chart(document.getElementById("chart-eval-trend"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Regression pass rate %", data: daily.map(d => d.regression_pass_rate_pct), borderColor: COLORS.green, backgroundColor: "transparent", tension: 0.2 },
        { label: "Golden-set accuracy %", data: daily.map(d => d.golden_set_accuracy_pct), borderColor: COLORS.blue, backgroundColor: "transparent", tension: 0.2 },
      ],
    },
    options: baseLineOpts(),
  });

  const releaseTable = document.getElementById("release-table");
  const rows = (data.release_events || []).map(rel => {
    const ts = new Date(rel.ts);
    const badgeClass = rel.event_type === "rollback" ? "sev-1" : "sev-2";
    return `<tr>
        <td>${rel.event_id}</td>
        <td><span class="sev-badge ${badgeClass}">${rel.event_type}</span></td>
        <td>${rel.artefact}</td>
        <td>${rel.from_version} → ${rel.to_version}</td>
        <td>${ts.toISOString().slice(0, 16).replace("T", " ")}</td>
        <td>${rel.golden_set_accuracy_pct}%</td>
        <td>${rel.regression_test_pass_rate_pct}%</td>
        <td>${rel.notes}</td>
      </tr>`;
  }).join("");
  releaseTable.innerHTML = `<thead><tr>
      <th>ID</th><th>Type</th><th>Artefact</th><th>Version change</th><th>Timestamp (UTC)</th><th>Golden-set</th><th>Regression pass</th><th>Notes</th>
    </tr></thead><tbody>${rows}</tbody>`;
}

function wireTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
      // Charts created while their tab was display:none get sized to 0×0 by Chart.js.
      // Nudging a resize once the tab is visible forces every chart on it to recalculate
      // its canvas size and actually draw.
      window.dispatchEvent(new Event("resize"));
    });
  });
}

main().catch(err => {
  document.querySelector("main").innerHTML =
    `<div class="panel" style="color:#E08585;">Failed to load dashboard data: ${err.message}. If viewing this file directly via file://, serve it over a local HTTP server instead (browsers block fetch() of local JSON from file://).</div>`;
  console.error(err);
});
