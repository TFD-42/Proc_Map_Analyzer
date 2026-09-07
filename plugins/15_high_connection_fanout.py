"""Flags a process talking to an unusually large number of distinct
remote endpoints at once -- the shape of a scanner, a proxy, a P2P
client, or beaconing malware alike. Legitimate load balancers, browsers
with many tabs, and package managers mid-download also produce fan-out,
so this labels the pattern, not the cause.
"""
from __future__ import annotations

_FANOUT_THRESHOLD = 15


def enrich(process_info):
    remotes = {
        conn["raddr"] for conn in (process_info.get("connections") or [])
        if conn.get("raddr")
    }
    if len(remotes) < _FANOUT_THRESHOLD:
        return {}
    return {
        "notice": "high connection fan-out",
        "distinct_remote_endpoints": len(remotes),
    }
