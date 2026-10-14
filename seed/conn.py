"""The one place a FalkorDB connection is configured (seed CLIs, scenario and the backend all use it).

FALKORDB_HOST / FALKORDB_PORT (default localhost:6379), optional FALKORDB_USERNAME / FALKORDB_PASSWORD, and
FALKORDB_TLS=1 for a TLS endpoint such as FalkorDB Cloud.
"""
import os

from dotenv import load_dotenv
from falkordb import FalkorDB


def connect():
    load_dotenv()
    return FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")),
                    username=os.getenv("FALKORDB_USERNAME") or None, password=os.getenv("FALKORDB_PASSWORD") or None,
                    ssl=os.getenv("FALKORDB_TLS", "").lower() in ("1", "true", "yes"))
