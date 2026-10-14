"""Loads the Kestrel Pay seed into a throwaway graph 'kestrel_pay_test' (never touches 'kestrel_pay')."""
import os
import time
from contextlib import contextmanager

import pytest

os.environ["TENANTS"] = "kestrel_pay,kestrel_pay_test"  # read by backend.db at call time

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
