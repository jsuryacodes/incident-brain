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


EVAL = "__eval_"  # internal twin graphs for the scenario eval: <tenant>__eval_<scenario id>; never served over HTTP


def eval_twin(tenant, scenario_id):
    return f"{tenant}{EVAL}{scenario_id}"


def base_tenant(name):
    """The tenant a (twin) graph name belongs to: 'kestrel_pay__nomem' / 'kestrel_pay__eval_x' -> 'kestrel_pay'."""
    if name.endswith(NOMEM):
        return name[:-len(NOMEM)]
    if EVAL in name:
        base, sid = name.split(EVAL, 1)
        return base if sid else name  # a twin needs a scenario id
    return name


def get_graph(tenant):
    if base_tenant(tenant) not in allowed_tenants():
        raise ValueError(f"unknown tenant {tenant!r}; allowed: {allowed_tenants()}")
    return client().select_graph(tenant)
