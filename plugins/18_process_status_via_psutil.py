"""Looks up the live process STATUS (running / sleeping / zombie /
stopped / disk-sleep...) via psutil, using only the pid from
process_info -- an example of a plugin reaching beyond the fields it was
handed. psutil is guaranteed present here: it's the parent tool's own
runtime dependency, so it's already importable in the plugin's process.
Most useful for zombie/stopped detection, which the base collector
doesn't expose today.
"""
from __future__ import annotations

import psutil


def enrich(process_info):
    pid = process_info.get("pid")
    if pid is None:
        return {}
    try:
        status = psutil.Process(pid).status()
    except psutil.ZombieProcess:
        return {"status": "zombie", "notice": "process is a zombie (exited but not reaped by its parent)"}
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {}

    result = {"status": status}
    if status == psutil.STATUS_STOPPED:
        result["notice"] = f"process is {status}"
    return result
