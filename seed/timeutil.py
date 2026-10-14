"""Relative time helpers. All seed times are integer epoch seconds (UTC), relative to NOW."""
import time
from datetime import datetime, timezone

NOW = int(time.time())


def set_now(epoch=None):
    """Must be called BEFORE the data package is imported (data computes times at import)."""
    global NOW
    NOW = int(epoch if epoch is not None else time.time())
    return NOW


def ago(days=0, hours=0, minutes=0):
    return NOW - int(days * 86400 + hours * 3600 + minutes * 60)


def stamp(ts):
    """Epoch -> 'YYYY-MM-DD HH:MM' (UTC), for chat transcripts."""
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M")
