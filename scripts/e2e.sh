#!/usr/bin/env bash
# End-to-end check of the web UI in a real (headless) browser, in one command:
#   scripts/e2e.sh                 build the frontend, re-seed both tenants + the story (mock), start the app,
#                                  run Playwright (theme, story replay, Brain, Explorer, screenshots, gate, fresh runs)
#   E2E_BASE_URL=http://localhost:8000 scripts/e2e.sh --no-server   test an app that is already running (e.g. docker compose)
# Mock mode only: no API key, no paid calls. Screenshots land in docs/screenshots/.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${E2E_PORT:-8765}"
export E2E_CODE="${E2E_CODE:-e2e-code}"
[ -x .venv/bin/python ] || { echo "run scripts/setup.sh first"; exit 1; }
(cd frontend && { [ -d node_modules ] || npm ci; } && npx playwright install chromium >/dev/null && npm run build)
if [ "${1:-}" != "--no-server" ]; then
  echo "==> fresh seed + the story (mock)"
  .venv/bin/python -m backend.demo story --quiet >/dev/null
  export E2E_BASE_URL="http://127.0.0.1:$PORT"
  LLM_MODE=mock ACCESS_CODE="$E2E_CODE" RATE_LIMIT_PER_MIN=100000 ANTHROPIC_API_KEY= \
    .venv/bin/uvicorn backend.api.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
  SERVER=$!
  trap 'kill $SERVER 2>/dev/null || true' EXIT
  for _ in $(seq 1 50); do curl -fs "$E2E_BASE_URL/api/health" >/dev/null && break; sleep 0.2; done
fi
echo "==> playwright against ${E2E_BASE_URL:-http://localhost:8000}"
(cd frontend && npx playwright test)
