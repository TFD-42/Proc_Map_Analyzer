"""Flags a process listening on 0.0.0.0 (or :: for IPv6) -- reachable
from every network interface, not just localhost. On a laptop that
usually means "more exposed than intended"; on an actual server it's
often exactly the point. Context (this machine's role) decides which;
this plugin only surfaces the fact and the port.
"""
from __future__ import annotations

_ALL_INTERFACES_HOSTS = {"0.0.0.0", "::", "[::]"}


def enrich(process_info):
    exposed_ports = []
    for conn in process_info.get("connections") or []:
        if (conn.get("status") or "").upper() != "LISTEN":
            continue
        laddr = conn.get("laddr") or ""
        host = laddr.rsplit(":", 1)[0] if ":" in laddr else laddr
        if host in _ALL_INTERFACES_HOSTS:
            port = laddr.rsplit(":", 1)[-1]
            exposed_ports.append(port)
    if not exposed_ports:
        return {}
    return {
        "notice": "listening on all interfaces (0.0.0.0)",
        "ports": sorted(set(exposed_ports)),
    }
