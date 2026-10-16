#!/usr/bin/env bash
# One-command live validation for later (NOT run unattended: it costs money). Needs ANTHROPIC_API_KEY in .env.
#   scripts/live-check.sh            # Haiku (claude-haiku-5-5), est. ~$0.15 (~₹13) in total, see docs/live-mode.md
#   MODEL=claude-sonnet-5-5 scripts/live-check.sh   # ~20x the cost; only for the demo recording
# Every run keeps the per-run budget guard (MAX_RUN_COST_USD, default $0.05) and prints its cost.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
grep -q '^ANTHROPIC_API_KEY=.\+' .env || { echo "no ANTHROPIC_API_KEY in .env: nothing to do"; exit 1; }
M="${MODEL:-claude-haiku-5-5}"
echo "==> 1. Firefighter on the hero alert (~5 calls)"
python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes" --live --model "$M"
python -m backend.agents.check_run "$(ls -t runs/firefighter-*.json | head -1)" || true
echo "==> 2. The same through MCP (~5 calls)"
python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx rate 12%" --live --model "$M" --tools-via mcp
echo "==> 3. Alert storm, live (~6 calls)"
python -m backend.demo storm --live --model "$M" --quiet
echo "==> 4. Scenario library + held-out, full profile only (~100 calls); results printed, docs untouched"
python -m backend.agents.firefighter_eval --live --model "$M" --profiles full --generated 0
