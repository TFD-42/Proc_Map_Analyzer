"""Flags a process combining sustained high CPU with an outbound
connection on a port conventionally used by cryptocurrency mining pools
(Stratum protocol). Port numbers are a weak signal on their own -- pools
also run on 443/80 specifically to blend in -- so this only fires on the
port+CPU combination, and still names it a heuristic, not a verdict.
"""
from __future__ import annotations

_MINING_PORTS = {3333, 4444, 5555, 7777, 8080, 8888, 9999, 14444, 45700}
_CPU_THRESHOLD = 50.0


def enrich(process_info):
    if (process_info.get("cpu_percent") or 0) < _CPU_THRESHOLD:
        return {}
    for conn in process_info.get("connections") or []:
        raddr = conn.get("raddr") or ""
        if ":" not in raddr:
            continue
        port = raddr.rsplit(":", 1)[1]
        if port.isdigit() and int(port) in _MINING_PORTS:
            return {
                "notice": "high CPU + connection on a common mining-pool port",
                "detail": f"cpu={process_info.get('cpu_percent')}%, remote={raddr}",
            }
    return {}
