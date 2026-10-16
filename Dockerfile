# Incident Brain: one container serving the web UI at / and the API at /api, on $PORT (default 8000).
#   docker build -t incident-brain .        (local stack with FalkorDB: docker compose up --build)
# Stage 1 builds frontend/dist; stage 2 is the Python runtime. Golden replays are baked in.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 LLM_MODE=mock
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY seed seed
COPY runs/golden runs/golden
COPY runs/eval runs/eval
COPY docs/schema.md docs/cypher.md docs/
COPY --from=ui /ui/dist frontend/dist
RUN useradd --create-home --uid 10001 app && chown -R app /app/runs
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",\"8000\")}/api/health').status == 200 else 1)"
CMD ["sh", "-c", "exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
