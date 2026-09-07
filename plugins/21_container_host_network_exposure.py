"""Flags a containerized process that's also listening on 0.0.0.0 --
worth knowing because it usually means the container runs with
`--net=host` (no network namespace isolation at all) or has that port
explicitly published to every host interface. Either is a normal,
deliberate choice for plenty of services; the point is making it visible
rather than assumed.
"""
from __future__ import annotations


def enrich(process_info):
    container = process_info.get("container")
    if not container:
        return {}
    listening_all = [
        conn["laddr"] for conn in (process_info.get("connections") or [])
        if (conn.get("status") or "").upper() == "LISTEN"
        and (conn.get("laddr") or "").startswith(("0.0.0.0:", "::", "[::]"))
    ]
    if not listening_all:
        return {}
    return {
        "notice": "containerized process listening on all interfaces",
        "container": container,
        "ports": listening_all,
    }
