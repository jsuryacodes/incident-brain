"""Kestrel Pay seed data. Import AFTER timeutil.set_now(): times are computed at import."""
from . import deploys, incidents, knowledge, org, services

_MODULES = [org, services, deploys, knowledge, incidents]
NODES = [n for m in _MODULES for n in m.NODES]
EDGES = [e for m in _MODULES for e in m.EDGES]
