"""Part F: the generated scale company and the timings in receipts."""
from collections import Counter

from seed.load import build


def test_scale_company_is_deterministic_and_valid():
    a, ae = build("scale_demo", 1_800_000_000)
    b, be = build("scale_demo", 1_800_000_000)
    assert [n["id"] for n in a] == [n["id"] for n in b] and len(ae) == len(be)  # same seed, same company
    labels, types = Counter(n["label"] for n in a), Counter(e[1] for e in ae)
    assert labels["Service"] == 2000 and 9000 <= types["DEPENDS_ON"] <= 11000 and labels["Person"] == 320


def test_receipts_carry_query_times(ctx):
    from backend.tools.registry import call
    out = call("blast_radius", {"service_id": "svc:config-service"}, ctx)
    assert all(q["ms"] >= 0 for q in out.receipt["queries"]) and out.receipt["ms"] >= 0
