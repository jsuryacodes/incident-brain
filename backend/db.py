"""One FalkorDB graph per tenant. Tenant allowlist comes from env TENANTS (comma-separated, default kestrel_pay,northwind_health)."""
import os

from dotenv import load_dotenv
from seed.conn import connect

load_dotenv()
_client = None


def allowed_tenants():
    return [t.strip() for t in os.getenv("TENANTS", "kestrel_pay,northwind_health").split(",") if t.strip()]


def client():
    global _client
    if _client is None:
        _client = connect()
    return _client


def redis():
    """The raw Redis connection FalkorDB runs on (API counters)."""
    return client().connection


NOMEM = "__nomem"  # internal twin graph for the "without memory" contrast run; never served over HTTP


def nomem_twin(tenant):
    return tenant + NOMEM


def get_graph(tenant):
    if (tenant[:-len(NOMEM)] if tenant.endswith(NOMEM) else tenant) not in allowed_tenants():
        raise ValueError(f"unknown tenant {tenant!r}; allowed: {allowed_tenants()}")
    return client().select_graph(tenant)
