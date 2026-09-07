"""Flags a process that (a) has an external (non-loopback) network
connection RIGHT NOW and (b) has already appeared, under the same
exe+name, in several of the tool's own past runs (--history / H29) --
a coarse, honestly-scoped proxy for "long-lived process quietly talking
outbound", which is the general shape of C2 beaconing.

This is NOT true beacon-interval detection (fixed-period connection
timing): the history snapshot (see snapshot_from_processes in the main
script) deliberately does not record per-connection timestamps, only
process identity/CPU/RAM per run -- so exact interval regularity isn't
reconstructable from it. What IS reconstructable and still useful: "this
same process, with an external connection, has now been seen across N
separate analysis runs" -- rules out one-off/transient connections
(a browser tab, a package manager checking for updates) without needing
new instrumentation. Treat a hit as "worth watching across future runs",
not proof of beaconing.

Reads outputs/history.json (the tool's own default --history-file path,
relative to the current working directory -- override with the
PROC_ANALYZER_HISTORY_FILE environment variable if analysis runs from a
different cwd than the history file's location). Missing/unreadable
history is the NORMAL case on a first run and is silently a no-op.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_MIN_APPEARANCES = 3  # counting this run: needs 2+ PRIOR runs plus this one


def _is_external(addr: str | None) -> bool:
    if not addr:
        return False
    host = addr.split(":")[0]
    return host not in ("127.0.0.1", "::1", "0.0.0.0", "", "localhost") and not host.startswith("::ffff:127.")


def _load_history() -> list[dict]:
    path = Path(os.environ.get("PROC_ANALYZER_HISTORY_FILE", "outputs/history.json"))
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def enrich(process_info):
    connections = process_info.get("connections") or []
    has_external_now = any(
        _is_external(c.get("raddr")) for c in connections
    )
    if not has_external_now:
        return {}

    exe = process_info.get("exe")
    name = process_info.get("name")
    if not exe and not name:
        return {}

    history = _load_history()
    if not history:
        return {}

    appearances = 0
    for snapshot in history:
        for p in snapshot.get("processes", []):
            if (exe and p.get("exe") == exe) or (not exe and p.get("name") == name):
                appearances += 1
                break  # count once per snapshot

    total_with_current = appearances + 1  # this run isn't in history.json yet
    if total_with_current < _MIN_APPEARANCES:
        return {}

    return {
        "notice": (
            f"same process (by {'exe' if exe else 'name'}) seen in {total_with_current} analysis runs "
            "while holding an external network connection -- long-lived outbound activity, worth "
            "watching across future runs (not proof of beaconing: exact connection timing isn't tracked)"
        ),
        "runs_observed": total_with_current,
    }
