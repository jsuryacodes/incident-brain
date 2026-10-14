#!/usr/bin/env bash
# One-shot setup on a fresh Mac/Linux box. Safe to re-run.
#   scripts/setup.sh
# venv (.venv, Python >= 3.10) -> pip install -r requirements.txt -> FalkorDB on :6379 -> seed both tenants -> verify.
set -euo pipefail
cd "$(dirname "$0")/.."

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# 1. Python >= 3.10. macOS ships /usr/bin/python3 = 3.9, and often no `python` at all, so look for a newer one.
say "Python"
PY=""
for c in python3.15 python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || die "need Python 3.10 or newer (found: $(python3 --version 2>&1 || echo none)). Install it: brew install python@3.12"
echo "using $PY ($("$PY" --version))"

# 2. venv + dependencies
say "Virtualenv .venv"
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo ".venv uses Python < 3.10; recreating it"; rm -rf .venv
fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "installed: $(.venv/bin/python -m pip freeze | wc -l | tr -d ' ') packages"
[ -f .env ] || { cp .env.example .env; echo "created .env from .env.example (mock mode, no API key needed)"; }

# 3. FalkorDB on localhost:6379 (Docker container 'falkordb')
say "FalkorDB"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Desktop, then re-run."
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop, then re-run."
if [ -n "$(docker ps -q -f name=^falkordb$)" ]; then
  echo "container 'falkordb' is running"
elif [ -n "$(docker ps -aq -f name=^falkordb$)" ]; then
  echo "starting the stopped container 'falkordb'"; docker start falkordb >/dev/null
else
  echo "creating container 'falkordb' (FalkorDB on :6379, Browser on :3000)"
  docker run -d --name falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest >/dev/null
fi
for i in $(seq 1 30); do
  .venv/bin/python -c 'from falkordb import FalkorDB; FalkorDB(host="localhost", port=6379).connection.ping()' 2>/dev/null && break
  [ "$i" = 30 ] && die "FalkorDB did not answer on localhost:6379 after 30s (is another Redis using the port?)"
  sleep 1
done
echo "FalkorDB answers on localhost:6379"

# 4. Seed + verify both tenants
for t in kestrel_pay northwind_health; do
  say "Seed + verify $t"
  .venv/bin/python -m seed.load --graph "$t" --reset
  .venv/bin/python -m seed.verify --graph "$t" | tail -1
done

say "Done"
echo "Next:  scripts/demo.sh            (the whole story, mock mode, free)"
echo "       source .venv/bin/activate && pytest -q"
