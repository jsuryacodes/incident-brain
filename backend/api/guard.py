"""API protection, all configured from env (read per request, so tests and ops can change it without a restart).

ACCESS_CODE        -> X-Access-Code header unlocks the live LLM and admin endpoints (constant-time compare).
                      Unset = live and admin are disabled for everyone.
DAILY_LIVE_RUNS    -> max live runs per UTC day (default 30): Redis INCR on ib:live_runs:<YYYY-MM-DD> with a TTL.
RATE_LIMIT_PER_MIN -> per-IP token bucket (default 20 requests/minute), in memory.
"""
import hmac
import os
import threading
import time
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from backend.db import redis


def code_ok(request: Request):
    expected, given = os.getenv("ACCESS_CODE", ""), request.headers.get("x-access-code", "")
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def require_code(request: Request):
    if not code_ok(request):
        raise HTTPException(403, "this endpoint needs a valid X-Access-Code header")


def live_key(now=None):
    return f"ib:live_runs:{datetime.fromtimestamp(now or time.time(), timezone.utc):%Y-%m-%d}"


def take_live_run():
    """Count one live run against today's cap. Raises 429 once the cap is used up."""
    cap = int(os.getenv("DAILY_LIVE_RUNS", "30"))
    key = live_key()
    n = redis().incr(key)
    if n == 1:
        redis().expire(key, 2 * 86400)
    if n > cap:
        raise HTTPException(429, f"daily live-run cap reached ({cap}); try mock mode or come back tomorrow")
    return n


def decide_mode(request: Request, want_live: bool):
    """-> (mode, reason). Live only with a correct access code, a key on the server and room under the daily cap."""
    if not want_live:
        return "mock", "mock mode (free); send live: true with an access code to use the real model"
    if not code_ok(request):
        return "mock", "no valid access code: running in mock mode"
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "mock", "the server has no ANTHROPIC_API_KEY: running in mock mode"
    take_live_run()
    return "live", "live model (access code accepted)"


class RateLimiter:
    """Token bucket per client IP: RATE_LIMIT_PER_MIN tokens, refilled continuously."""

    def __init__(self):
        self.buckets, self.lock = {}, threading.Lock()

    def allow(self, ip):
        rate = max(1, int(os.getenv("RATE_LIMIT_PER_MIN", "20")))
        now = time.monotonic()
        with self.lock:
            tokens, last = self.buckets.get(ip, (rate, now))
            tokens = min(rate, tokens + (now - last) * rate / 60)
            ok = tokens >= 1
            self.buckets[ip] = (tokens - 1 if ok else tokens, now)
            return ok
