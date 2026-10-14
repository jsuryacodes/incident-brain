"""Loads the Kestrel Pay seed into throwaway graphs (never touches 'kestrel_pay').
kestrel_pay_test: read-only tool tests. Tests that WRITE memory get their own graph from the `fresh` fixture."""
import os
import time
from contextlib import contextmanager

import pytest

SCRATCH = ["kestrel_pay_mem", "kestrel_pay_story", "kestrel_pay_nomem", "kestrel_pay_conc", "kestrel_pay_api",
           "kestrel_pay_brain", "kestrel_pay_brain2", "kestrel_pay_iso", "northwind_test"]
os.environ["TENANTS"] = ",".join(["kestrel_pay", "kestrel_pay_test"] + SCRATCH)  # read by backend.db at call time
os.environ["LLM_MODE"] = "mock"  # tests are always mock

from backend.db import get_graph  # noqa: E402
from backend.tools.receipt import ToolContext  # noqa: E402
from seed.load import load  # noqa: E402

TEST_GRAPH = "kestrel_pay_test"


@pytest.fixture(scope="session")
def now():
    return int(time.time())


@pytest.fixture(scope="session", autouse=True)
def seeded(now):
    load(TEST_GRAPH, reset=True, now=now, data_package="kestrel_pay", quiet=True)
    yield
    get_graph(TEST_GRAPH).delete()


@pytest.fixture()
def ctx(now):
    return ToolContext(tenant=TEST_GRAPH, now=now)


@pytest.fixture()
def graph():
    return get_graph(TEST_GRAPH)


@pytest.fixture()
def learned_edge(graph, now):
    """Context manager: write (risk-rules)-[:DEPENDS_ON {source:'learned'}]->(config-service), always remove it."""
    @contextmanager
    def cm():
        graph.query("MATCH (a:Service {id:'svc:risk-rules'}), (b:Service {id:'svc:config-service'}) "
                    "MERGE (a)-[r:DEPENDS_ON {source:'learned', kind:'sync', learned_at:$now}]->(b)", {"now": now})
        try:
            yield
        finally:
            graph.query("MATCH (:Service {id:'svc:risk-rules'})-[r:DEPENDS_ON {source:'learned'}]->(:Service {id:'svc:config-service'}) DELETE r")
    return cm


@pytest.fixture(scope="session")
def fresh():
    """fresh(name) -> name: (re)load the seed (northwind_* graphs get Northwind Health) into a scratch graph; all are
    deleted at the end."""
    made = []

    def make(name, pkg=None):
        assert name in SCRATCH
        load(name, reset=True, data_package=pkg or ("northwind_health" if name.startswith("northwind") else "kestrel_pay"), quiet=True)
        made.append(name)
        return name
    yield make
    for n in set(made):
        get_graph(n).delete()
