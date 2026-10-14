#!/usr/bin/env bash
# The web UI locally: build the frontend (if needed) and serve UI + API on one port.
#   scripts/ui.sh            -> http://localhost:8000      (PORT=8080 scripts/ui.sh for another port)
# Needs scripts/setup.sh first (venv + FalkorDB + seed). Mock mode; nothing here calls a paid API.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { echo "run scripts/setup.sh first"; exit 1; }
command -v npm >/dev/null || { echo "need Node >= 18 (brew install node)"; exit 1; }
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html 2>/dev/null | head -1)" ]; then
  (cd frontend && { [ -d node_modules ] || npm ci; } && npm run build)
fi
# The story's memory (Session 1, resolve, Session 2) so the Explorer and the Brain have something to show.
if [ "$(.venv/bin/python -c 'from backend.db import get_graph; print(get_graph("kestrel_pay").ro_query("MATCH (n {origin:\"agent\"}) RETURN count(n)").result_set[0][0])')" = "0" ]; then
  .venv/bin/python -m backend.demo story --quiet >/dev/null
fi
echo "Incident Brain UI: http://localhost:${PORT:-8000}"
exec .venv/bin/uvicorn backend.api.main:app --host 127.0.0.1 --port "${PORT:-8000}"
