"""One FalkorDB graph per tenant. Tenant allowlist comes from env TENANTS (comma-separated, default kestrel_pay)."""
import os

from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()
_client = None


def allowed_tenants():
    return [t.strip() for t in os.getenv("TENANTS", "kestrel_pay").split(",") if t.strip()]


def get_graph(tenant):
    if tenant not in allowed_tenants():
        raise ValueError(f"unknown tenant {tenant!r}; allowed: {allowed_tenants()}")
    global _client
    if _client is None:
        _client = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    return _client.select_graph(tenant)
