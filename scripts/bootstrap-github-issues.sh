#!/usr/bin/env bash
#
# Bootstraps the initial GitHub Issues backlog AND a Projects (v2) board for
# this repo, sourced directly from docs/roadmap.md (the addendum's 90-day
# plan) and training/reading/06-claude-code-production-build-plan.md (the
# mock-to-real migration phases).
#
# Prerequisites:
#   - GitHub CLI (`gh`) installed and authenticated: gh auth login
#   - The `project` OAuth scope granted: gh auth refresh -s project
#     (Projects v2 needs this in addition to the default `repo` scope —
#     without it, issue creation still works but item-add to the board fails.)
#   - Run from inside the cloned repo, AFTER the initial push, so `gh` can
#     infer the target repo from the git remote.
#
# Note: issue bodies are written to temp files and passed via --body-file,
# rather than inlined as $(cat <<'EOF' ... EOF) command-substitution
# arguments. macOS ships bash 3.2 by default (frozen since 2007), which has
# a known bug with heredocs nested inside command substitution used as
# repeated function arguments — this pattern avoids it entirely and is
# portable across bash versions.
#
# Usage:
#   chmod +x scripts/bootstrap-github-issues.sh
#   ./scripts/bootstrap-github-issues.sh

set -euo pipefail

OWNER="$(gh repo view --json owner -q .owner.login 2>/dev/null || echo "getamazednow")"
PROJECT_TITLE="GenAI Observability — Delivery Roadmap"

echo "Owner: $OWNER"
echo ""
echo "Creating labels (safe to re-run — existing labels are skipped)..."

create_label() {
  name="$1"; color="$2"; desc="$3"
  gh label create "$name" --color "$color" --description "$desc" 2>/dev/null \
    || echo "  label '$name' already exists, skipping"
}

create_label "phase-0-preflight"       "5319E7" "Human-only prerequisites before any agent/engineering work"
create_label "phase-1-instrumentation" "0E8A16" "Instrumentation scaffold (Weeks 0-2)"
create_label "phase-2-ingestion"       "0E8A16" "Ingestion wiring to a real Datadog org (Weeks 0-2)"
create_label "phase-3-dashboards"      "1D76DB" "Dashboards, monitors, SLOs (Weeks 3-6)"
create_label "phase-4-governance"      "D93F0B" "Governance and evaluation harness (Weeks 7-10)"
create_label "phase-5-scale"           "FBCA04" "Scale and reusability (Weeks 11-13)"
create_label "human-gate"              "B60205" "Requires named-human sign-off before proceeding"
create_label "agent-executable"        "C2E0C6" "Scoped for delegation to an engineering agent"
create_label "repo-hygiene"            "BFD4F2" "Housekeeping: templates, protections, contributor docs"

echo ""
echo "Creating Projects (v2) board '$PROJECT_TITLE'..."

PROJECT_NUMBER=""
PROJECT_URL=""
if PROJECT_JSON=$(gh project create --owner "$OWNER" --title "$PROJECT_TITLE" --format json 2>/dev/null); then
  PROJECT_NUMBER=$(printf '%s' "$PROJECT_JSON" | grep -oE '"number":[0-9]+' | head -1 | grep -oE '[0-9]+')
  PROJECT_URL=$(printf '%s' "$PROJECT_JSON" | grep -oE '"url":"[^"]+"' | head -1 | sed -E 's/"url":"(.*)"/\1/')
  echo "  created project #$PROJECT_NUMBER: $PROJECT_URL"
  echo "  default Status field ships with Todo / In Progress / Done — rename 'Todo' to 'Backlog' in the UI if you want that exact wording."
else
  echo "  WARNING: could not create project board (missing 'project' scope? run: gh auth refresh -s project)."
  echo "  Continuing — issues will still be created, just not added to a board."
fi

echo ""
echo "Creating issues..."

issue_exists() {
  title="$1"
  gh issue list --state all --limit 200 --json title -q '.[].title' 2>/dev/null \
    | grep -qxF "$title"
}

create_issue() {
  title="$1"; labels="$2"; body_file="$3"
  if issue_exists "$title"; then
    echo "  skip (already exists): $title"
    return 0
  fi
  url=$(gh issue create --title "$title" --label "$labels" --body-file "$body_file")
  echo "  created: $url"
  if [ -n "$PROJECT_NUMBER" ]; then
    if gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$url" >/dev/null 2>&1; then
      echo "    added to project #$PROJECT_NUMBER"
    else
      echo "    WARNING: could not add to project (check 'project' auth scope)"
    fi
  fi
}

BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

cat > "$BODY_FILE" <<'EOF'
**Goal:** complete the non-delegable prerequisites before any real instrumentation work starts (per `training/reading/06-claude-code-production-build-plan.md`, Phase 0).

**Checklist:**
- [ ] Named owner assigned per accountability layer — Architecture, Platform Engineering, Cyber Security, Data Governance, Responsible AI/Risk, Product Owner (see `docs/metrics-catalogue.md`)
- [ ] Risk tier defined for the pilot workflow (Order Support & Returns Assistant)
- [ ] Redaction/retention policy signed off by Data Governance and Legal
- [ ] Datadog org provisioned with LLM Observability + APM entitlements
- [ ] Least-privilege service account created for CI (dashboards/monitors/SLOs import only — not full org admin)
- [ ] Approved model/tool registry defined for the pilot workflow

**Not agent-executable.** This is a human governance step — do not proceed to Phase 1 until closed.

**Maps to:** roadmap Weeks 0–2 foundation (`docs/roadmap.md`).
EOF
create_issue "[Phase 0] Preflight: owners, risk tier, redaction policy, Datadog org provisioning" "phase-0-preflight,human-gate" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** replace `data/generator/generate_synthetic_data.py` with real instrumentation code, without touching production traffic yet.

**Task:** using `docs/datadog-mapping.md` as the field-level contract, scaffold Datadog LLM/Agent Observability SDK (or OpenTelemetry GenAI semantic-convention) instrumentation for the Order Support & Returns Assistant workflow. Emit spans for `workflow`, `llm`, `retrieval`, `tool` and `guardrail` matching the exact field names in `data/synthetic/raw/*.csv`. Write to local OTLP export or console exporter for validation — do not connect to a live Datadog org yet. Include unit tests asserting every required field from the telemetry contract table is present on each span type.

**Human gate:** review that span field names match the contract 1:1 before any real ingestion is enabled; confirm no prompt/output content is logged unredacted.

**Depends on:** Phase 0 preflight closed.
**Maps to:** roadmap Weeks 0–2 foundation.
EOF
create_issue "[Phase 1] Instrumentation scaffold: replace synthetic generator with real spans" "phase-1-instrumentation,agent-executable" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** point the Phase 1 instrumentation at a real, non-production Datadog environment.

**Task:** wire the Phase 1 instrumentation to the Datadog Agent or OTel Collector using staging Datadog org credentials (supplied via the operator's own secrets mechanism — never committed, never requested in chat/agent context). Validate that `genai.workflow.count`, `genai.llm.call.count`, `genai.tool.call.count` and `genai.guardrail.decision.count` appear in Datadog's Metrics Explorer within 5 minutes of a test workflow run. Do not point at the production Datadog org.

**Human gate:** confirm staging data looks correct before promoting the same config to production; confirm redaction is actually being applied to logged content, not just planned.

**Depends on:** #2 (instrumentation scaffold).
**Maps to:** roadmap Weeks 0–2 foundation.
EOF
create_issue "[Phase 2] Ingestion wiring: point instrumentation at a staging Datadog org" "phase-2-ingestion,agent-executable" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** replace the local-JSON static dashboard with native Datadog dashboards, and make the monitor/SLO definitions live — in staging only.

**Task:** import all 7 templates in `datadog/dashboards/*.json` into the staging Datadog org via the Dashboards API or `datadog_dashboard` Terraform resource, adapting metric names to whatever Phase 1/2 instrumentation actually emits. Import `datadog/monitors/*.json` and `datadog/slos/*.json` similarly. Leave all monitor `notify` targets pointed at a staging Slack channel, not the real on-call rotation.

**Human gate:** Platform Engineering validates dashboard queries against known-good staging traffic.

**Depends on:** #3 (ingestion wiring).
**Maps to:** roadmap Weeks 3–6 operate.
EOF
create_issue "[Phase 3] Import dashboards, monitors and SLOs into staging Datadog" "phase-3-dashboards,agent-executable" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** promote validated staging monitors to production alert routing.

**Task:** open a dedicated, reviewed PR to re-point `notify` targets at the real on-call rotation (e.g. `@pagerduty-genai-oncall`, `@security-oncall`). This must be its own change — do not bundle it into the dashboard/monitor import (#4).

**Human gate:** this is itself the human gate — requires sign-off from whoever owns the on-call rotation before merge.

**Depends on:** #4 (dashboard/monitor import validated in staging).
**Maps to:** roadmap Weeks 3–6 operate.
EOF
create_issue "[Phase 3b] Re-point monitor alerts to real on-call rotation" "phase-3-dashboards,human-gate" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** close the single biggest gap this repo is explicit about — replace the synthetic evaluation-harness series with a real one.

**Governance decision required first (not agent-executable):** choose Datadog Managed Evaluations vs. a custom LLM-as-judge pipeline; curate golden sets; set human-review sampling rate and reviewer assignment. Owned by Responsible AI/Risk and Data Governance, not engineering.

**Narrow, supporting agent task (once methodology is decided):** scaffold the plumbing to call the chosen evaluation service on a schedule against sampled production traffic, and emit `genai.eval.groundedness_score`, `genai.eval.citation_accuracy_score`, `genai.eval.hallucination_flag`, `genai.eval.regression_pass_rate` and `genai.eval.golden_set_accuracy` in the same shape the RAG and Release dashboards already expect.

**Human gate:** Responsible AI/Risk signs off on the evaluation methodology before its output is used to gate any release — i.e. before regression-pass-rate is wired into an actual release-blocking check.

**Maps to:** roadmap Weeks 7–10 govern.
EOF
create_issue "[Phase 4] Real evaluation harness: replace synthetic eval series" "phase-4-governance,human-gate" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** close the gap list called out in `docs/metrics-catalogue.md` — dimensions not yet modelled even in synthetic form:

- [ ] Bias/fairness flags
- [ ] Refusal quality
- [ ] Human override rate

**Task:** extend `data/generator/generate_synthetic_data.py` to produce a believable synthetic series for these three dimensions, add corresponding panels to the Security & Responsible AI dashboard, and document the field additions in `docs/datadog-mapping.md` so the real-instrumentation contract stays complete.

**Maps to:** roadmap Weeks 7–10 govern.
EOF
create_issue "[Phase 4] Model the remaining governance gaps: bias/fairness, refusal quality, override rate" "phase-4-governance" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** create reusable platform patterns so a second/third use case onboards with materially less effort.

**Task:** extract the Phase 1–3 instrumentation, dashboard templates and monitor/SLO templates into a versioned internal package (or shared repo) with parameterised `use_case`, `tenant` and `risk_tier` values. Write an onboarding checklist a second team could follow without platform-engineering hand-holding. Do not change the underlying telemetry contract while doing this — packaging only, not schema redesign.

**Human gate/acceptance test:** a second, genuinely different use case attempts onboarding using only the checklist, with Platform Engineering observing but not intervening. If intervention is needed, the checklist has a gap.

**Maps to:** roadmap Weeks 11–13 scale.
EOF
create_issue "[Phase 5] Extract into a reusable instrumentation library and onboarding checklist" "phase-5-scale,agent-executable" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** match the governance posture this repo demonstrates — require review before merge, even solo.

**Task:** Settings → Branches → add rule for `main` → require a pull request before merging, require status checks (Pages deploy workflow) to pass before merge.
EOF
create_issue "[Repo hygiene] Branch protection + required PR review on main" "repo-hygiene" "$BODY_FILE"

cat > "$BODY_FILE" <<'EOF'
**Goal:** make the repo collaboration-ready for architecture-board / CoP contributors, not just publication-ready.

**Task:** add `CONTRIBUTING.md` (how to regenerate synthetic data, how to propose a new dashboard/metric), `.github/ISSUE_TEMPLATE/` (bug / enhancement / new-metric-proposal), and a PR template referencing the phase labels above.
EOF
create_issue "[Repo hygiene] Add CONTRIBUTING.md and issue/PR templates" "repo-hygiene" "$BODY_FILE"

rm -f "$BODY_FILE"
trap - EXIT

echo ""
echo "Done."
if [ -n "$PROJECT_NUMBER" ]; then
  echo "Board: $PROJECT_URL"
else
  echo "No board was created — see the warning above. You can retry with: gh project create --owner $OWNER --title '$PROJECT_TITLE'"
fi
