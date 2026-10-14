"""python -m backend.tools <tool> '<json args>' [--tenant kestrel_pay] [--receipt]"""
import argparse
import json
import sys

from backend.tools.receipt import ToolContext
from backend.tools.registry import TOOLS, call


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.tools")
    ap.add_argument("tool", nargs="?")
    ap.add_argument("args", nargs="?", default="{}", help="JSON object of tool arguments")
    ap.add_argument("--tenant", default="kestrel_pay")
    ap.add_argument("--receipt", action="store_true", help="also print the receipt (queries + highlight)")
    a = ap.parse_args()
    if not a.tool:
        print("tools:")
        for n, t in TOOLS.items():
            print(f"  {n:28s} {t['description'].split('.')[0]}.")
        return
    try:
        args = json.loads(a.args)
    except json.JSONDecodeError as e:
        sys.exit(f"args must be a JSON object: {e}")
    out = call(a.tool, args, ToolContext(tenant=a.tenant))
    dump = lambda o: json.dumps(o, indent=2, ensure_ascii=False, default=str)
    print("RESULT" + (f" ({len(json.dumps(out.result))} chars)" if a.receipt else ""))
    print(dump(out.result))
    if a.receipt:
        print("\nRECEIPT")
        print(dump(out.receipt))


if __name__ == "__main__":
    main()
