#!/usr/bin/env bash
# The demo story in mock mode (free): Session 1, resolve, Session 2, and Session 2 without memory for contrast.
#   scripts/demo.sh            every tool call
#   scripts/demo.sh --quiet    only session headers, handoffs and the before/after box
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { echo "No .venv yet: run scripts/setup.sh first." >&2; exit 1; }
source .venv/bin/activate
exec python -m backend.demo story --compare-no-memory "$@"
